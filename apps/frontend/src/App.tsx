import { BrowserRouter } from 'react-router-dom';
import { ProductRoutes } from '@/routes/ProductRoutes';
import { MapViewProvider } from '@/state/mapViewContext';

export default function App() {
  return (
    <BrowserRouter>
      <MapViewProvider>
        <ProductRoutes />
      </MapViewProvider>
    </BrowserRouter>
  );
}
