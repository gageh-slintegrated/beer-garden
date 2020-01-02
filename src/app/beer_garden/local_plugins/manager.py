# -*- coding: utf-8 -*-

import json
import logging
import string
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from random import choice
from types import ModuleType
from typing import Dict

import sys
from brewtils.specification import _SYSTEM_SPEC
from brewtils.stoppable_thread import StoppableThread

import beer_garden
import beer_garden.config
from beer_garden.errors import PluginValidationError
from beer_garden.local_plugins import ConfigKeys, CONFIG_NAME
from beer_garden.local_plugins.env_help import expand_string_with_environment_var
from beer_garden.local_plugins.plugin_runner import PluginRunner


@dataclass
class Runner:
    instance: PluginRunner
    instance_id: str = ""
    restart: bool = False
    dead: bool = False


class RunnerManager(StoppableThread):
    """Manages creation and destruction of PluginRunners"""

    logger = logging.getLogger(__name__)
    runners = {}

    _instance = None

    def __init__(
        self,
        plugin_dir=None,
        log_dir=None,
        connection_info=None,
        username=None,
        password=None,
    ):
        self.display_name = "Runner Manager"

        self._plugin_path = Path(plugin_dir) if plugin_dir else None
        self._log_dir = log_dir
        self._connection_info = connection_info
        self._username = username
        self._password = password

        super().__init__(logger=self.logger, name="RunnerManager")

    def run(self):
        self.logger.info(self.display_name + " is started")

        while not self.wait(1):
            self.monitor()

        self.logger.info(self.display_name + " is stopped")

    def monitor(self):
        """Make sure runners stay alive

        Iterate through all plugins, testing them one at a time.

        If any of them are dead restart them, otherwise just keep chugging along.
        """
        for runner_id, runner in self.runners.items():
            if self.stopped():
                break

            if runner.instance.process.poll() is not None:
                if runner.restart:
                    self.logger.warning(f"Runner {runner_id} stopped, restarting")
                    self.restart(runner_id)
                elif not runner.dead:
                    self.logger.warning(f"Runner {runner_id} is dead, not restarting")
                    runner.dead = True

    @classmethod
    def current_paths(cls):
        return [r.instance.process_cwd for r in cls.runners.values()]

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = cls(
                plugin_dir=beer_garden.config.get("plugin.local.directory"),
                log_dir=beer_garden.config.get("plugin.local.log_directory"),
                connection_info=beer_garden.config.get("entry.http"),
                username=beer_garden.config.get("plugin.local.auth.username"),
                password=beer_garden.config.get("plugin.local.auth.password"),
            )
        return cls._instance

    @classmethod
    def start_all(cls):
        for runner in cls.runners.values():
            runner.instance.start()

    @classmethod
    def stop_all(cls):
        """Attempt to stop all plugins."""
        from time import sleep
        sleep(1)

        for runner_id in cls.runners:
            cls.stop_one(runner_id)

    @classmethod
    def stop_one(cls, runner_id):
        runner = cls.runners[runner_id]

        if not runner.instance.is_alive():
            cls.logger.info(f"Runner {runner_id} was already stopped")
            return

        # try:
        #     cls.logger.info(f"About to stop runner {runner_id}")
        #     runner.terminate(timeout=3)
        # except subprocess.TimeoutExpired:
        #     cls.logger.error(f"Runner {runner_id} didn't terminate, about to kill")
        #     runner.kill()

    @classmethod
    def remove(cls, runner_id):
        del cls.runners[runner_id]

    @classmethod
    def restart(cls, runner_id):
        old_runner = cls.runners[runner_id]

        new_runner = PluginRunner(
            runner_id=old_runner.runner_id,
            process_args=old_runner.process_args,
            process_cwd=old_runner.process_cwd,
            process_env=old_runner.process_env,
        )

        cls.runners[runner_id] = new_runner

        new_runner.start()

    def load_new(self, path: str = None) -> None:
        """Create PluginRunners for all plugins in a directory

        Note: This scan does not walk the directory tree - all plugins must be
        in the top level of the given path.

        Args:
            path: The path to scan for plugins. If none will default to the
                plugin path specified at initialization.
        """
        plugin_path = path or self._plugin_path

        for path in plugin_path.iterdir():
            try:
                if path.is_dir() and path not in self.current_paths():
                    self.runners.update(self.create_runners(path))
            except Exception as ex:
                self.logger.exception(f"Error loading plugin at {path}: {ex}")

    def create_runners(self, plugin_path: Path) -> Dict[str, Runner]:
        """Creates PluginRunners for a particular plugin directory

        It will use the validator to validate the plugin before registering the
        plugin in the database as well as adding an entry to the plugin map.

        Args:
            plugin_path: The path of the plugin

        Returns:
            A list of plugin runners

        """
        config_file = plugin_path / CONFIG_NAME

        if not plugin_path:
            raise PluginValidationError(f"Plugin path {plugin_path} does not exist")
        if not plugin_path.is_dir():
            raise PluginValidationError(f"Plugin path {plugin_path} is not a directory")
        if not config_file.exists():
            raise PluginValidationError(f"Config file {config_file} does not exist")
        if not config_file.is_file():
            raise PluginValidationError(f"Config file {config_file} is not a file")

        try:
            plugin_config = ConfigLoader.load(config_file)
        except PluginValidationError as ex:
            self.logger.error(f"Error loading config for plugin at {plugin_path}: {ex}")
            return {}

        new_runners = {}

        for instance_name in plugin_config["INSTANCES"]:
            runner_id = "".join([choice(string.ascii_letters) for _ in range(10)])
            process_args = self._process_args(plugin_config, instance_name)
            process_env = self._environment(
                plugin_config, instance_name, plugin_path, runner_id
            )

            new_runners[runner_id] = Runner(
                instance=PluginRunner(
                    runner_id=runner_id,
                    process_args=process_args,
                    process_cwd=plugin_path,
                    process_env=process_env,
                )
            )

        return new_runners

    @staticmethod
    def _process_args(plugin_config, instance_name):
        process_args = [sys.executable]

        if plugin_config.get("PLUGIN_ENTRY"):
            process_args += plugin_config["PLUGIN_ENTRY"].split(" ")
        elif plugin_config.get("NAME"):
            process_args += ["-m", plugin_config["NAME"]]
        else:
            raise PluginValidationError("Can't generate process args")

        plugin_args = plugin_config["PLUGIN_ARGS"].get(instance_name)
        if plugin_args:
            process_args += plugin_args

        return process_args

    def _environment(self, plugin_config, instance_name, plugin_path, runner_id):
        env = {}

        # System info comes from config file
        for key in _SYSTEM_SPEC:
            key = key.upper()

            if key in plugin_config:
                env["BG_" + key] = plugin_config.get(key)

        # Connection info comes from Beer-garden config
        env.update(
            {
                "BG_HOST": self._connection_info.host,
                "BG_PORT": self._connection_info.port,
                "BG_URL_PREFIX": self._connection_info.url_prefix,
                "BG_SSL_ENABLED": self._connection_info.ssl.enabled,
                "BG_CA_CERT": self._connection_info.ssl.ca_cert,
                "BG_CA_VERIFY": False,  # TODO - Fix this
            }
        )

        # The rest
        env.update(
            {
                "BG_INSTANCE_NAME": instance_name,
                "BG_RUNNER_ID": runner_id,
                "BG_PLUGIN_PATH": plugin_path.resolve(),
                "BG_USERNAME": self._username,
                "BG_PASSWORD": self._password,
            }
        )

        if "LOG_LEVEL" in plugin_config:
            env["BG_LOG_LEVEL"] = plugin_config["LOG_LEVEL"]

        # ENVIRONMENT from beer.conf
        for key, value in plugin_config.get("ENVIRONMENT", {}).items():
            env[key] = expand_string_with_environment_var(str(value), env)

        # Ensure values are all strings
        for key, value in env.items():
            env[key] = json.dumps(value) if isinstance(value, dict) else str(value)

        return env


class ConfigLoader(object):
    @staticmethod
    def load(config_file: Path) -> dict:
        """Loads a plugin config"""

        config_module = ConfigLoader._config_from_beer_conf(config_file)

        ConfigLoader._validate(config_module, config_file.parent)

        config = {}
        for key in ConfigKeys:
            if hasattr(config_module, key.name):
                config[key.name] = getattr(config_module, key.name)

        # Instances and arguments need some normalization
        config.update(
            ConfigLoader._normalize_instance_args(config.get("INSTANCES"), config.get("PLUGIN_ARGS"))
        )

        return config

    @staticmethod
    def _config_from_beer_conf(config_file: Path) -> ModuleType:
        """Load a beer.conf file as a Python module"""

        # Need to construct our own Loader here, the default doesn't work with .conf
        loader = SourceFileLoader("bg_plugin_config", str(config_file))
        spec = spec_from_file_location("bg_plugin_config", config_file, loader=loader)
        config_module = module_from_spec(spec)
        spec.loader.exec_module(config_module)

        return config_module

    @staticmethod
    def _normalize_instance_args(instances, args):
        """Normalize the different ways instances and arguments can be specified"""
        if instances is None and args is None:
            instances = ["default"]
            args = {"default": None}

        elif args is None:
            args = {}
            for instance_name in instances:
                args[instance_name] = None

        elif instances is None:
            if isinstance(args, list):
                instances = ["default"]
                args = {"default": args}
            elif isinstance(args, dict):
                instances = list(args.keys())
            else:
                raise ValueError(f"PLUGIN_ARGS must be list or dict, found {type(args)}")

        elif isinstance(args, list):
            temp_args = {}
            for instance_name in instances:
                temp_args[instance_name] = args

            args = temp_args

        else:
            raise PluginValidationError("Invalid INSTANCES and PLUGIN_ARGS combination")

        return {"INSTANCES": instances, "PLUGIN_ARGS": args}

    @staticmethod
    def _validate(config_module: ModuleType, path: Path) -> None:
        """Validate a plugin directory is valid

        Args:
            config_module: Configuration module to validate
            path: Path to directory containing plugin

        Returns:
            None

        Raises:
            PluginValidationError: Validation was not successful

        """
        ConfigLoader._entry_point(config_module, path)
        ConfigLoader._instances(config_module)
        ConfigLoader._args(config_module)
        ConfigLoader._environment(config_module)

    @staticmethod
    def _entry_point(config_module, path: Path) -> None:
        """Validates a plugin's entry point.

        An entry point is considered valid if the config has an entry with key
        PLUGIN_ENTRY and the value is a path to either a file or the name of a runnable
        Python module.
        """
        entry_point = getattr(config_module, ConfigKeys.PLUGIN_ENTRY.name, None)

        if not entry_point:
            return

        if (path / entry_point).is_file():
            return

        entry_parts = entry_point.split(" ")
        pkg = entry_parts[1] if entry_parts[0] == "-m" else entry_parts[0]
        pkg_path = path / pkg

        if (
            pkg_path.is_dir()
            and (pkg_path / "__init__.py").is_file()
            and (pkg_path / "__main__.py").is_file()
        ):
            return

        raise PluginValidationError(
            f"{ConfigKeys.PLUGIN_ENTRY.name} '{entry_point}' must be a Python file or a "
            f"runnable package"
        )

    @staticmethod
    def _instances(config_module) -> None:
        instances = getattr(config_module, ConfigKeys.INSTANCES.name, None)

        if instances is not None and not isinstance(instances, list):
            raise PluginValidationError(
                f"Invalid {ConfigKeys.INSTANCES.name} entry '{instances}': if present it "
                f"must be a list"
            )

    @staticmethod
    def _args(config_module) -> None:
        args = getattr(config_module, ConfigKeys.PLUGIN_ARGS.name, None)

        if args is None:
            return

        if isinstance(args, list):
            ConfigLoader._individual_args(args)

        elif isinstance(args, dict):
            instances = getattr(config_module, ConfigKeys.INSTANCES.name)

            for instance_name, instance_args in args.items():
                if instances is not None and instance_name not in instances:
                    raise PluginValidationError(
                        f"{ConfigKeys.PLUGIN_ARGS.name} contains key '{instance_name}' but "
                        f"that instance is not in {ConfigKeys.INSTANCES.name}"
                    )

                ConfigLoader._individual_args(instance_args)

            if instances:
                for instance_name in instances:
                    if instance_name not in args.keys():
                        raise PluginValidationError(
                            f"{ConfigKeys.INSTANCES.name} contains '{instance_name}' but "
                            f"that instance is not in {ConfigKeys.PLUGIN_ARGS.name}"
                        )

        else:
            raise PluginValidationError(
                f"Invalid {ConfigKeys.PLUGIN_ARGS.name} '{args}': must be a list or dict"
            )

    @staticmethod
    def _individual_args(args) -> None:
        """Validates an individual PLUGIN_ARGS entry"""
        if args is None:
            return

        if not isinstance(args, list):
            raise PluginValidationError(
                f"Invalid {ConfigKeys.PLUGIN_ARGS.name} entry '{args}': must be a list"
            )

        for arg in args:
            if not isinstance(arg, str):
                raise PluginValidationError(
                    f"Invalid plugin argument '{arg}': must be a string"
                )

    @staticmethod
    def _environment(config_module) -> None:
        """Validates ENVIRONMENT if specified.

        ENVIRONMENT must be a dictionary of Strings to Strings. Otherwise it is invalid.
        """
        env = getattr(config_module, ConfigKeys.ENVIRONMENT.name, None)

        if env is None:
            return

        if not isinstance(env, dict):
            raise PluginValidationError(
                f"Invalid {ConfigKeys.ENVIRONMENT.name} entry '{env}': if present it must "
                f"be a dict"
            )

        for key, value in env.items():
            if not isinstance(key, str):
                raise PluginValidationError(
                    f"Invalid {ConfigKeys.ENVIRONMENT.name} key '{key}': must be a string"
                )

            if not isinstance(value, str):
                raise PluginValidationError(
                    f"Invalid {ConfigKeys.ENVIRONMENT.name} value '{value}': must be a string"
                )

            if key.startswith("BG_"):
                raise PluginValidationError(
                    f"Invalid {ConfigKeys.ENVIRONMENT.name} key '{key}': Can't specify an "
                    f"environment variable with a 'BG_' prefix as it can mess with "
                    f"internal Beer-garden machinery. Sorry about that :/"
                )
