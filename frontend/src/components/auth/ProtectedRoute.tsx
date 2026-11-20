
import { Navigate, Outlet } from "react-router-dom";
import { useUser } from "../../context/UserContext";
import {
  hasPermission,
  type AppPermission,
} from "../../context/permissions";

interface ProtectedRouteProps {
  permission: AppPermission;
}

function ProtectedRoute({ permission }: ProtectedRouteProps) {
  const { activeUser, isLoading } = useUser();

  if (isLoading) {
    return <p>Loading your session...</p>;
  }

  if (!activeUser) {
    return <Navigate to="/login" replace />;
  }

  const isAuthorised = hasPermission(
    activeUser.role,
    permission
  );

  if (!isAuthorised) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}

export default ProtectedRoute;
