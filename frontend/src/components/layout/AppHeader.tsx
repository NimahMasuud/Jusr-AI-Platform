
import { Search, Bell, Menu, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useUser } from "../../context/UserContext";
import LanguageSwitcher from "../shared/LanguageSwitcher";

interface AppHeaderProps {
  onMenuClick: () => void;
}

function formatRole(role: string): string {
  const roleLabels: Record<string, string> = {
    coordinator: "Coordinator",
    referring_clinician: "Referring Clinician",
    receiving_clinician: "Receiving Clinician",
    facility_administrator: "Facility Administrator",
  };

  return roleLabels[role] ?? role;
}

function getInitials(name: string): string {
  return name
    .replace(/^Dr\s+/i, "")
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function AppHeader({ onMenuClick }: AppHeaderProps) {
  const { activeUser, logoutUser } = useUser();
  const navigate = useNavigate();

  function handleLogout() {
    logoutUser();
    navigate("/login", { replace: true });
  }

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="mobile-menu-button"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu size={22} />
        </button>

        <div className="header-search">
          <Search size={18} />
          <input
            type="search"
            placeholder="Search cases, patients..."
            aria-label="Search cases and patients"
          />
          <kbd>⌘ K</kbd>
        </div>
      </div>

      <div className="header-right">
        <LanguageSwitcher />
        {activeUser && (
          <>
            <div
              className="facility-context"
              aria-label={`Facility ID: ${activeUser.facility.id || "Not assigned"}`}
            >
              <span className="facility-indicator" />
              <span>
                {activeUser.facility.name}
              </span>
            </div>

            <button
              className="notification-button"
              aria-label="Notifications"
            >
              <Bell size={20} />
              <span className="notification-dot" />
            </button>

            <div className="header-divider" />

            <div className="profile-button">
              <div className="profile-avatar">
                {getInitials(activeUser.name)}
              </div>

              <div className="profile-details">
                <span className="profile-name">
                  {activeUser.name}
                </span>
                <span className="profile-role">
                  {formatRole(activeUser.role)}
                </span>
              </div>
            </div>

            <button
              type="button"
              className="notification-button"
              onClick={handleLogout}
              aria-label="Log out"
              title="Log out"
            >
              <LogOut size={19} />
            </button>
          </>
        )}
      </div>
    </header>
  );
}

export default AppHeader;
