import MapPage from '@/pages/MapPage';
import { MapViewProvider } from '@/state/mapViewContext';

export default function App() {
  return (
    <MapViewProvider>
      <MapPage />
    </MapViewProvider>
  );
}
