export function canManageProjects(user) {
  return ['admin', 'analyst'].includes(user?.role);
}
