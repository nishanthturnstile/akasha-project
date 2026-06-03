export type ActiveMapTool = 'measure' | 'field-draw' | 'field-edit' | null;

export type MapToolOwner = Exclude<ActiveMapTool, null>;
