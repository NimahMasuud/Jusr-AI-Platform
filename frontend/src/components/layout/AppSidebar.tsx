import {
  LayoutDashboard,
  ClipboardList,
  Users,
  ArrowLeftRight,
  Activity,
  MessageSquare,
  Sparkles,
  ChartNoAxesCombined,
  Building2,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";

import type { LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";
import logo from "../../assets/jusr-logo-cropped.png";

import { useUser } from "../../context/UserContext";
import { hasPermission, type AppPermission } from "../../context/permissions";

interface AppSidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onClose: () => void;
}

interface NavigationItem {
  label: string;
  path: string;
  icon: LucideIcon;
  permission: AppPermission;
}

interface NavigationSection {
  title: string;
  items: NavigationItem[];
}

const navigation: NavigationSection[] = [
  {
    title: "WORKSPACE",
    items: [
      {
        label: "Overview",
        path: "/dashboard",
        icon: LayoutDashboard,
        permission: "dashboard",
      },
      {
        label: "Worklist",
        path: "/worklist",
        icon: ClipboardList,
        permission: "worklist",
      },

      {
        label: "Incoming Urgent Cases",
        path: "/urgent-inbox",
        icon: Activity,
        permission: "urgent_inbox",
      },

      {
        label: "Patients",
        path: "/patients",
        icon: Users,
        permission: "patients",
      },
      {
        label: "Referrals",
        path: "/referrals",
        icon: ArrowLeftRight,
        permission: "referrals",
      },
      {
        label: "Consultations",
        path: "/consultations",
        icon: MessageSquare,
        permission: "consultations",
      },
      {
        label: "AI review",
        path: "/ai-review",
        icon: Sparkles,
        permission: "ai_review",
      },
    ],
  },
  {
    title: "INSIGHTS & ADMIN",
    items: [
      {
        label: "Measures",
        path: "/measures",
        icon: ChartNoAxesCombined,
        permission: "measures",
      },
      {
        label: "Facilities",
        path: "/facilities",
        icon: Building2,
        permission: "facilities",
      },
      {
        label: "Settings",
        path: "/settings",
        icon: Settings,
        permission: "settings",
      },
    ],
  },
];

function AppSidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onClose,
}: AppSidebarProps) {
  const { activeUser } = useUser();

if (!activeUser) {
  return null;
}

  // Display only sections containing permitted navigation items
  const visibleNavigation = navigation
    .map((section) => ({
      ...section,
      items: section.items.filter((item) =>
        hasPermission(activeUser.role, item.permission),
      ),
    }))
    .filter((section) => section.items.length > 0);

  return (
    <>
      {mobileOpen && <div className="sidebar-overlay" onClick={onClose} />}

      <aside
        className={`app-sidebar ${
          collapsed ? "sidebar-collapsed" : ""
        } ${mobileOpen ? "sidebar-mobile-open" : ""}`}
      >
        {/* BRAND */}
        <div className="sidebar-brand">
          <NavLink to="/dashboard" className="brand-link" onClick={onClose}>
            <img src={logo} alt="Jusr AI" className="brand-logo" />
          </NavLink>

          <button
            className="sidebar-close mobile-only"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        {/* ROLE-BASED NAVIGATION */}
        <nav className="sidebar-navigation">
          {visibleNavigation.map((section) => (
            <div className="nav-section" key={section.title}>
              {!collapsed && (
                <p className="nav-section-title">{section.title}</p>
              )}

              {section.items.map((item) => {
                const Icon = item.icon;

                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/dashboard"}
                    onClick={onClose}
                    className={({ isActive }) =>
                      `nav-item ${isActive ? "nav-item-active" : ""}`
                    }
                    title={collapsed ? item.label : undefined}
                  >
                    <Icon size={19} strokeWidth={1.8} />
                    {!collapsed && <span>{item.label}</span>}
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        {/* SIDEBAR FOOTER */}
        <div className="sidebar-footer">
          <NavLink
            to="/help-support"
            onClick={onClose}
            className={({ isActive }) =>
              `nav-item help-link ${isActive ? "nav-item-active" : ""}`
            }
            title={collapsed ? "Help & Support" : undefined}
          >
            <HelpCircle size={19} />
            {!collapsed && <span>Help & Support</span>}
          </NavLink>

          <button
            className="collapse-button desktop-only"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}

            {!collapsed && <span>Collapse sidebar</span>}
          </button>
        </div>
      </aside>
    </>
  );
}

export default AppSidebar;
