import { useEffect } from 'react';
import { BrowserRouter, useLocation, useNavigate } from 'react-router-dom';
import { ProductRoutes } from '@/routes/ProductRoutes';
import { MapViewProvider } from '@/state/mapViewContext';
import { setUnauthorizedHandler } from '@/lib/api';
import { queryClient } from '@/lib/queryClient';

function AuthEvents() {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (location.pathname === '/login' || location.pathname === '/signup') return;
      const returnTo = `${location.pathname}${location.search}${location.hash}`;
      queryClient.clear();
      navigate(`/login?returnTo=${encodeURIComponent(returnTo)}`, { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [location.hash, location.pathname, location.search, navigate]);

  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthEvents />
      <MapViewProvider>
        <ProductRoutes />
      </MapViewProvider>
    </BrowserRouter>
  );
}
