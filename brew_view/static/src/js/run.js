import _ from 'lodash';
import {camelCaseKeys, responseState} from './services/utility_service.js';

appRun.$inject = [
  '$rootScope',
  '$state',
  '$stateParams',
  '$http',
  '$q',
  'localStorageService',
  'UtilityService',
  'SystemService',
  'UserService',
  'TokenService',
  'RoleService',
];

/**
 * appRun - Runs the front-end application.
 * @param  {$rootScope} $rootScope         Angular's $rootScope object.
 * @param  {$state} $state                 Angular's $state object.
 * @param  {$stateParams} $stateParams     Angular's $stateParams object.
 * @param  {$http} $http                   Angular's $http object.
 * @param  {$q} $q                         Angular's $q object.
 * @param  {localStorageService} localStorageService Storage service
 * @param  {UtilityService} UtilityService Service for configuration/icons.
 * @param  {SystemService} SystemService   Service for System information.
 * @param  {UserService} UserService       Service for User information.
 * @param  {TokenService} TokenService     Service for User information.
 * @param  {RoleService} RoleService       Service for Role information.
 */
export function appRun(
    $rootScope,
    $state,
    $stateParams,
    $http,
    $q,
    localStorageService,
    UtilityService,
    SystemService,
    UserService,
    TokenService,
    RoleService) {
  $rootScope.$state = $state;
  $rootScope.$stateParams = $stateParams;

  $rootScope.loginInfo = {};
  $rootScope.showLogin = false;
  $rootScope.loginError = false;
  $rootScope.badPassword = false;

  // Change this to point to the Brew-View backend if it's at another location
  $rootScope.apiBaseUrl = '';

  $rootScope.config = {};
  $rootScope.systems = [];

  $rootScope.themes = {
    'default': false,
    'slate': false,
  };

  $rootScope.responseState = responseState;

  $rootScope.doLoad = function() {
    $rootScope.configPromise = UtilityService.getConfig()
    .then(
      (response) => {
        angular.extend($rootScope.config, camelCaseKeys(response.data));
      },
      (response) => {
        return $q.reject(response);
      }
    );

    $rootScope.systemsPromise = SystemService.getSystems(false, 'id,name,version')
    .then(
      (response) => {
        $rootScope.systems = response.data;
      },
      (response) => {
        // This is super annoying.
        // If any controller is actually using this promise we need to return a
        // rejection here, otherwise the chained promise will actually resolve
        // (success callback will be invoked instead of failure callback).
        // But for controllers that don't care if this fails (like the landing
        // controller) this causes a 'possibly unhandled rejection' since they
        // haven't constructed a pipeline based on this promise.
        return $q.reject(response);
      }
    );
  };

  $rootScope.doLogin = function() {
    TokenService.doLogin(
        $rootScope.loginInfo.username,
        $rootScope.loginInfo.password).then(
      (response) => {
        $rootScope.loginInfo = {};
        $rootScope.showLogin = false;
        $rootScope.badPassword = false;

        TokenService.handleRefresh(response.data.refresh);
        TokenService.handleToken(response.data.token);

        UserService.loadUser(response.data.token).then(
          (response) => {
            $rootScope.user = response.data;

            // coalescePermissions [0] is the roles, [1] is the permissions
            let perms = RoleService.coalescePermissions($rootScope.user.roles);
            $rootScope.user.permissions = perms[1];

            $rootScope.doLoad();
            $rootScope.$broadcast('userChange');

            $rootScope.changeTheme($rootScope.user.preferences.theme || 'default');
          }, (response) => {
            console.log('error loading user');
          }
        );
      }, (response) => {
        console.log('bad login');
        $rootScope.badPassword = true;
        $rootScope.loginInfo.password = undefined;
      }
    );
  };

  $rootScope.doLogout = function() {
    let refreshToken = localStorageService.get('refresh');
    if (refreshToken) {
      TokenService.clearRefresh(refreshToken);
      localStorageService.remove('refresh');
    }

    localStorageService.remove('token');
    $http.defaults.headers.common.Authorization = undefined;

    $rootScope.user = undefined;
    $rootScope.doLoad();
    $rootScope.$broadcast('userChange');
  };

  $rootScope.hasPermission = function(permission) {
    return _.includes($rootScope.user.permissions, permission) ||
      _.includes($rootScope.user.permissions, 'bg-all');
  };

  $rootScope.changeTheme = function(theme, sendUpdate) {
    localStorageService.set('currentTheme', theme);
    for (const key of Object.keys($rootScope.themes)) {
      $rootScope.themes[key] = (key == theme);
    };

    if ($rootScope.user && sendUpdate) {
      UserService.setTheme($rootScope.user.id, theme);
    }
  };

  $rootScope.toggleLogin = function() {
    // Clicking should always clear the red outline
    $rootScope.loginError = false;
    $rootScope.showLogin = !$rootScope.showLogin;
  };

  // Load up some settings
  // If we have a token use it to load a user
  // If not, try to load a persistent theme
  let token = localStorageService.get('token');
  if (token) {
    TokenService.handleToken(token);
    UserService.loadUser(token).then(
      (response) => {
        $rootScope.user = response.data;
        $rootScope.changeTheme($rootScope.user.preferences.theme || 'default');
      }, (response) => {
        console.log('error loading user');
      }
    );
  } else {
    $rootScope.changeTheme(localStorageService.get('currentTheme') || 'default');
  }

  const isLaterVersion = function(system1, system2) {
    let versionParts1 = system1.version.split('.');
    let versionParts2 = system2.version.split('.');

    for (let i = 0; i < 3; i++) {
      if (parseInt(versionParts1[i]) > parseInt(versionParts2[i])) {
        return true;
      }
    }
    return false;
  };

  /**
   * Converts a system's version to the 'latest' semantic url scheme.
   * @param {Object} system  - system for which you want the version URL.
   * @return {string} - either the systems version or 'latest'.
   */
  $rootScope.getVersionForUrl = function(system) {
    for (let sys of $rootScope.systems) {
      if (sys.name == system.name) {
        if (isLaterVersion(sys, system)) {
          return system.version;
        }
      }
    }
    return 'latest';
  };

  /**
   * Convert a system ObjectID to a route to use for the router.
   * @param {string} systemId  - ObjectID for system.
   * @return {string} url to use for UI routing.
   */
  $rootScope.getSystemUrl = function(systemId) {
    for (let system of $rootScope.systems) {
      if (system.id == systemId) {
        let version = this.getVersionForUrl(system);
        return '/systems/' + system.name + '/' + version;
      }
    }
    return '/systems';
  };

  /**
   * Find the system with the specified name/version (version can just
   * be the string 'latest')
   *
   * @param {string} name - The name of the system you wish to find.
   * @param {string} version - The version you want to find (or latest)
   * @return {Object} The latest system or undefined if it is not found.
   */
  $rootScope.findSystem = function(name, version) {
    let notFound = {
      data: {message: 'No matching system'},
      errorGroup: 'system',
      status: 404,
    };

    return $rootScope.systemsPromise.then(
      () => {
        if (version !== 'latest') {
          let sys = _.find($rootScope.systems, {name: name, version: version});

          if (_.isUndefined(sys)) {
            return $q.reject(notFound);
          } else {
            return $q.resolve(sys);
          }
        }

        let filteredSystems = _.filter($rootScope.systems, {name: name});
        if (_.isEmpty(filteredSystems)) {
          return $q.reject(notFound);
        }

        let latestSystem = filteredSystems[0];
        for (let system of $rootScope.systems) {
          if (isLaterVersion(system, latestSystem)) {
            latestSystem = system;
          }
        }

        return $q.resolve(latestSystem);
      }
    );
  };


  /**
   * Find the system with the given ID.
   * @param {string} systemId - System's ObjectID
   * @return {Object} the system with this ID.
   */
  $rootScope.findSystemByID = function(systemId) {
    for (let system of $rootScope.systems) {
      if (system.id === systemId) {
        return system;
      }
    }
  };

  $rootScope.doLoad();
};


dtLoadingTemplate.$inject = ['DTDefaultOptions'];
/**
 * dtLoadingTemplate - Loading Template for datatabales
 * @param  {Object} DTDefaultOptions Data-tables default options.
 */
export function dtLoadingTemplate(DTDefaultOptions) {
  DTDefaultOptions.setLoadingTemplate('<div class="row"><loading loader="queues"></loading></div>');
};
