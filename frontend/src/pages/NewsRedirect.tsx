import { Navigate, useParams, useSearchParams } from 'react-router-dom';

/** Legacy /news/:id → /episode/:id (preserving ?podcast=). The episode detail lives at /episode/:id now. */
export const NewsRedirect: React.FC = () => {
  const { id } = useParams();
  const [params] = useSearchParams();
  const podcast = params.get('podcast');
  const to = `/episode/${encodeURIComponent(id || '')}${podcast ? `?podcast=${encodeURIComponent(podcast)}` : ''}`;
  return <Navigate to={to} replace />;
};

export default NewsRedirect;
