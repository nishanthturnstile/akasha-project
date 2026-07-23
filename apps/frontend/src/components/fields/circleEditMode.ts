import distance from '@turf/distance';
import type { Polygon, Position } from 'geojson';
import {
  TerraDrawExtend,
  type GeoJSONStoreFeatures,
  type GeoJSONStoreGeometries,
  type TerraDrawAdapterStyling,
  type TerraDrawMouseEvent,
} from 'terra-draw';
import {
  buildCircleRing,
  cardinalHandlePositions,
  clamp,
  deriveCircleFromRing,
  HANDLE_ROLES,
  pointInRing,
  type HandleRole,
} from '@/components/fields/circleGeometry';

const { TerraDrawBaseDrawMode, getDefaultStyling } = TerraDrawExtend;

type FeatureId = TerraDrawExtend.FeatureId;

const MIN_RADIUS_METERS = 5;
const MAX_RADIUS_METERS = 20000;

interface CircleEditStyling extends TerraDrawExtend.CustomStyling {
  handleColor: TerraDrawExtend.HexColorStyling;
  handleOutlineColor: TerraDrawExtend.HexColorStyling;
  handleWidth: TerraDrawExtend.NumericStyling;
}

export interface CircleEditModeOptions extends TerraDrawExtend.BaseModeOptions<CircleEditStyling> {
  targetFeatureId?: FeatureId;
}

/**
 * Custom TerraDraw mode: edits a circle-shaped polygon feature via 4 cardinal (N/E/S/W)
 * resize handles, with whole-shape move by dragging the body -- no separate center handle.
 * Registered permanently alongside the other modes; which feature it targets is pushed in
 * live via `TerraDraw.updateModeOptions('circle-edit', { targetFeatureId })`.
 *
 * Handle features are created once per target and only ever have their geometry patched in
 * place on drag -- never removed/recreated mid-drag, since doing so would drop pointer
 * capture and silently truncate the gesture after a single move.
 */
export class TerraDrawCircleEditMode extends TerraDrawBaseDrawMode<CircleEditStyling> {
  mode = 'circle-edit';

  private targetFeatureId: FeatureId | undefined;
  private center: Position | undefined;
  private radiusMeters = 0;
  private handleIds: FeatureId[] = [];

  private dragMode: 'move' | 'resize' | null = null;
  private dragStartPointer: Position | null = null;
  private dragStartCenter: Position | null = null;

  updateOptions(options?: CircleEditModeOptions) {
    super.updateOptions(options);
    if (options && 'targetFeatureId' in options) {
      this.setTarget(options.targetFeatureId);
    }
  }

  private setTarget(featureId: FeatureId | undefined) {
    this.removeHandles();
    this.targetFeatureId = featureId;
    if (featureId === undefined || this.state === 'unregistered' || this.state === 'registered') {
      return;
    }
    this.rebuildFromTarget();
  }

  private rebuildFromTarget() {
    if (this.targetFeatureId === undefined) return;
    const geometry = this.readTargetGeometry();
    if (!geometry) return;
    const params = deriveCircleFromRing(geometry.coordinates[0] as Position[]);
    if (!params) return;
    this.center = params.center;
    this.radiusMeters = params.radiusMeters;
    this.createHandles();
  }

  private readTargetGeometry(): Polygon | null {
    if (this.targetFeatureId === undefined) return null;
    try {
      const geometry = this.store.getGeometryCopy<GeoJSONStoreGeometries>(this.targetFeatureId);
      return geometry.type === 'Polygon' ? geometry : null;
    } catch {
      return null;
    }
  }

  private createHandles() {
    if (!this.center) return;
    const positions = cardinalHandlePositions(this.center, this.radiusMeters);
    this.handleIds = this.store.create(
      positions.map((position, i) => ({
        geometry: { type: 'Point', coordinates: position },
        properties: { mode: this.mode, role: HANDLE_ROLES[i] },
      })),
    );
  }

  private removeHandles() {
    if (this.handleIds.length) {
      try {
        this.store.delete(this.handleIds);
      } catch {
        // Already gone (e.g. the target feature itself was deleted).
      }
    }
    this.handleIds = [];
    this.center = undefined;
    this.radiusMeters = 0;
  }

  /** @internal */
  start() {
    this.setStarted();
    if (this.targetFeatureId !== undefined && !this.center) {
      this.rebuildFromTarget();
    }
  }

  /** @internal */
  stop() {
    this.cleanUp();
    this.setStopped();
  }

  /** @internal */
  cleanUp() {
    this.removeHandles();
    this.dragMode = null;
    this.dragStartPointer = null;
    this.dragStartCenter = null;
  }

  private handleAtPixel(event: TerraDrawMouseEvent): HandleRole | null {
    if (!this.center) return null;
    const positions = cardinalHandlePositions(this.center, this.radiusMeters);
    for (let i = 0; i < positions.length; i++) {
      const screen = this.project(positions[i][0], positions[i][1]);
      const dx = screen.x - event.containerX;
      const dy = screen.y - event.containerY;
      if (Math.sqrt(dx * dx + dy * dy) <= this.pointerDistance) {
        return HANDLE_ROLES[i];
      }
    }
    return null;
  }

  private isInsideBody(event: TerraDrawMouseEvent): boolean {
    const geometry = this.readTargetGeometry();
    if (!geometry) return false;
    return pointInRing([event.lng, event.lat], geometry.coordinates[0] as Position[]);
  }

  /** @internal */
  onDragStart(event: TerraDrawMouseEvent, setMapDraggability: (enabled: boolean) => void) {
    if (!this.center || this.targetFeatureId === undefined) return;

    if (this.handleAtPixel(event)) {
      this.dragMode = 'resize';
      setMapDraggability(false);
      return;
    }
    if (this.isInsideBody(event)) {
      this.dragMode = 'move';
      this.dragStartPointer = [event.lng, event.lat];
      this.dragStartCenter = this.center;
      setMapDraggability(false);
      return;
    }
    this.dragMode = null;
    setMapDraggability(true);
  }

  /** @internal */
  onDrag(event: TerraDrawMouseEvent, setMapDraggability: (enabled: boolean) => void) {
    if (!this.dragMode || !this.center || this.targetFeatureId === undefined) return;
    setMapDraggability(false);

    if (this.dragMode === 'resize') {
      const meters = distance(this.center, [event.lng, event.lat], { units: 'kilometers' }) * 1000;
      this.radiusMeters = clamp(meters, MIN_RADIUS_METERS, MAX_RADIUS_METERS);
    } else if (this.dragStartPointer && this.dragStartCenter) {
      const dLng = event.lng - this.dragStartPointer[0];
      const dLat = event.lat - this.dragStartPointer[1];
      this.center = [this.dragStartCenter[0] + dLng, this.dragStartCenter[1] + dLat];
    }

    this.applyGeometry();
  }

  /** @internal */
  onDragEnd(_event: TerraDrawMouseEvent, setMapDraggability: (enabled: boolean) => void) {
    this.dragMode = null;
    this.dragStartPointer = null;
    this.dragStartCenter = null;
    setMapDraggability(true);
  }

  private applyGeometry() {
    if (!this.center || this.targetFeatureId === undefined) return;
    const ring = buildCircleRing(this.center, this.radiusMeters);
    const handlePositions = cardinalHandlePositions(this.center, this.radiusMeters);
    this.store.updateGeometry([
      { id: this.targetFeatureId, geometry: { type: 'Polygon', coordinates: [ring] } },
      ...this.handleIds.map((id, i) => ({
        id,
        geometry: { type: 'Point' as const, coordinates: handlePositions[i] },
      })),
    ]);
  }

  /** @internal */
  styleFeature(feature: GeoJSONStoreFeatures): TerraDrawAdapterStyling {
    const styles = getDefaultStyling();
    if (feature.geometry.type === 'Point') {
      styles.pointColor = this.getHexColorStylingValue(this.styles.handleColor, '#f59e0b', feature);
      styles.pointOutlineColor = this.getHexColorStylingValue(
        this.styles.handleOutlineColor,
        '#ffffff',
        feature,
      );
      styles.pointWidth = this.getNumericStylingValue(this.styles.handleWidth, 6, feature);
      styles.pointOutlineWidth = 1.5;
      styles.zIndex = 50;
    }
    return styles;
  }

  validateFeature() {
    return { valid: true as const };
  }
}
