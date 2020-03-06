import re

from setuptools import setup, find_packages

with open("README.rst") as readme_file:
    readme = readme_file.read()


def find_version(version_file):
    version_line = open(version_file, "rt").read()
    match_object = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_line, re.M)

    if not match_object:
        raise RuntimeError("Unable to find version string in %s" % version_file)

    return match_object.group(1)


setup(
    name="beer-garden",
    version=find_version("beer_garden/__version__.py"),
    description="Beergarden Application",
    long_description=readme,
    author="The Beer Garden Team",
    author_email="beer@beer-garden.io",
    url="https://beer-garden.io",
    packages=(find_packages(exclude=["test", "test.*"])),
    license="MIT",
    keywords="beer beer-garden beergarden",
    install_requires=[
        "apispec==0.38.0",
        "apscheduler==3.6.0",
        "brewtils>=3.0.0a1",
        "mongoengine<0.16",
        "passlib<1.8",
        "prometheus-client==0.7.1",
        "pyrabbit2==1.0.7",
        "pytz<2019",
        "ruamel.yaml<0.16",
        "tornado==6.0.3",
        "yapconf>=0.3.5",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    entry_points={
        "console_scripts": [
            "generate_config=beer_garden.__main__:generate_config",
            "migrate_config=beer_garden.__main__:migrate_config",
            "generate_log_config=beer_garden.__main__:generate_logging_config",
            "beergarden=beer_garden.__main__:main",
        ]
    },
)
