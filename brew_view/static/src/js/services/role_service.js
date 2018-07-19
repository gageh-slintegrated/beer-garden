import _ from 'lodash';

roleService.$inject = ['$http'];

/**
 * roleService - Service for interacting with the role API.
 * @param  {$http} $http Angular's $http Object.
 * @return {Object}      Service for interacting with the role API.
 */
export default function roleService($http) {
  let service = {
    getRole: (roleId) => {
      return $http.get('api/v1/roles/' + roleId);
    },
    deleteRole: (roleId) => {
      return $http.delete('api/v1/roles/' + roleId);
    },
    updateRole: (roleId, operations) => {
      return $http.patch('api/v1/roles/' + roleId, {operations: operations});
    },
    getRoles: () => {
      return $http.get('api/v1/roles/');
    },
    createRole: (name, permissions, roles) => {
      return $http.post('api/v1/roles/', {
        name: name,
        permissions: permissions,
        roles: roles,
      });
    },
  };

  function coalesce_permissions(role_list) {

    if (!role_list) {
      return [[], []];
    }

    let aggregate_roles = [];
    let aggregate_perms = [];

    for (let role of role_list) {
      aggregate_roles.push(role.name);
      aggregate_perms = _.union(aggregate_perms, role.permissions);

      let recursed = coalesce_permissions(role.roles);
      aggregate_roles = _.union(aggregate_roles, recursed[0]);
      aggregate_perms = _.union(aggregate_perms, recursed[1]);
    }

    return [aggregate_roles, aggregate_perms];
  }

  _.assign(service, {
    addPermission: (roleId, permission) => {
      return service.updateRole(roleId, [
        {operation: 'add', path: '/permissions', value: permission},
      ]);
    },
    removePermission: (roleId, permission) => {
      return service.updateRole(roleId, [
        {operation: 'remove', path: '/permissions', value: permission},
      ]);
    },
    setPermissions: (roleId, permissions) => {
      return service.updateRole(roleId, [
        {operation: 'set', path: '/permissions', value: permissions},
      ]);
    },
    addRole: (roleId, role) => {
      return service.updateRole(roleId, [
        {operation: 'add', path: '/roles', value: role},
      ]);
    },
    removeRole: (roleId, role) => {
      return service.updateRole(roleId, [
        {operation: 'remove', path: '/roles', value: role},
      ]);
    },
    setRoles: (roleId, roles) => {
      return service.updateRole(roleId, [
        {operation: 'set', path: '/roles', value: roles},
      ]);
    },
    coalesce_permissions: coalesce_permissions,
  });

  return service;
};
