/**
 * Human-friendly labels for field metadata keys used across filter and form UI.
 * Keeps product terminology ("Crop", "Season") instead of raw camelCase keys.
 */
const FIELD_LABELS: Record<string, string> = {
  groupName: 'Group',
  cropType: 'Crop',
  variety: 'Variety',
  seasonLabel: 'Season',
  activityType: 'Activity',
  assignee: 'Assignee',
  status: 'Status',
  sowingDate: 'Sowing date',
  plantingDate: 'Planting date',
};

/**
 * Resolve a friendly label for a metadata key. Falls back to a title-cased,
 * space-separated rendering for unknown keys.
 */
export function fieldLabel(key: string): string {
  if (FIELD_LABELS[key]) {
    return FIELD_LABELS[key];
  }
  const spaced = key.replace(/([A-Z])/g, ' $1').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
