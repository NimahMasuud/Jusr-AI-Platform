
import { useState } from "react";
import { Outlet } from "react-router-dom";
import { AlertCircle } from "lucide-react";

import AppSidebar from "./AppSidebar";
import AppHeader from "./AppHeader";

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="app-layout">
      <AppSidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
      />

      <div
        className={`app-main ${
          collapsed ? "main-expanded" : ""
        }`}
      >
        <AppHeader
          onMenuClick={() => setMobileOpen(true)}
        />

        <div
          role="status"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
            padding: "12px 24px",
            background: "#FFF8E7",
            borderBottom: "1px solid #F2D89B",
            color: "#79540B",
          }}
        >
          <AlertCircle size={19} />

          <div>
            <strong>Demonstration environment — simulated data</strong>
            <p style={{ margin: "3px 0 0", fontSize: "13px" }}>
              This application uses synthetic records and simulated
              workflows. It is not connected to live hospital systems.
            </p>
          </div>
        </div>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
