"use client";

import Link from "next/link";
import { useState } from "react";

const mockTenants = [
  { id: "t1", name: "Acme Corp", logo: "🚀", theme: "blue" },
  { id: "t2", name: "Globex Inc", logo: "🌍", theme: "green" },
  { id: "t3", name: "Initech", logo: "🏢", theme: "purple" },
];

export default function AgencyDashboard() {
  const [activeTenant, setActiveTenant] = useState(mockTenants[0]);
  const [isEditingTheme, setIsEditingTheme] = useState(false);

  return (
    <div className="min-h-screen bg-apple-bg p-8">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Coming Soon Banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-apple p-4 text-center">
          <p className="text-sm font-medium text-amber-800">
            Agency Mode is coming soon. The preview below shows sample data only.{" "}
            <Link href="/dashboard" className="text-apple-blue hover:underline">
              Go to Dashboard
            </Link>
          </p>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between bg-apple-card p-6 rounded-apple shadow-apple opacity-75 pointer-events-none select-none">
          <div>
            <h1 className="text-2xl font-semibold text-apple-text tracking-tight">
              Agency Portal
            </h1>
            <p className="text-apple-secondary mt-1">
              Preview workspace for future agency mode. Sample data is shown until live agency APIs are connected.
            </p>
          </div>
          
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-apple-secondary">
              Active Client:
            </span>
            <select
              className="py-2 pl-3 pr-8 w-48"
              value={activeTenant.id}
              onChange={(e) => {
                const tenant = mockTenants.find((t) => t.id === e.target.value);
                if (tenant) setActiveTenant(tenant);
              }}
            >
              {mockTenants.map((tenant) => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.logo} {tenant.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Main Content Grid (preview only) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 opacity-75 pointer-events-none select-none">
          {/* Client Overview */}
          <div className="md:col-span-2 space-y-6">
            <div className="bg-apple-card rounded-apple shadow-apple p-8">
              <div className="flex items-center gap-4 mb-8">
                <div className="w-16 h-16 rounded-2xl bg-apple-bg flex items-center justify-center text-3xl shadow-inner">
                  {activeTenant.logo}
                </div>
                <div>
                  <h2 className="text-2xl font-semibold text-apple-text">
                    {activeTenant.name}
                  </h2>
                  <p className="text-apple-secondary">Workspace Overview</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-apple-sm border border-apple-border/50 bg-apple-bg/50">
                  <div className="text-sm text-apple-secondary mb-1">Active Campaigns</div>
                  <div className="text-2xl font-semibold text-apple-text">12</div>
                </div>
                <div className="p-4 rounded-apple-sm border border-apple-border/50 bg-apple-bg/50">
                  <div className="text-sm text-apple-secondary mb-1">Posts Scheduled</div>
                  <div className="text-2xl font-semibold text-apple-text">48</div>
                </div>
                <div className="p-4 rounded-apple-sm border border-apple-border/50 bg-apple-bg/50">
                  <div className="text-sm text-apple-secondary mb-1">Audience Growth</div>
                  <div className="text-2xl font-semibold text-green-600">+14%</div>
                </div>
                <div className="p-4 rounded-apple-sm border border-apple-border/50 bg-apple-bg/50">
                  <div className="text-sm text-apple-secondary mb-1">Engagement Rate</div>
                  <div className="text-2xl font-semibold text-apple-text">4.2%</div>
                </div>
              </div>
            </div>
          </div>

          {/* Theme Settings */}
          <div className="space-y-6">
            <div className="bg-apple-card rounded-apple shadow-apple p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-apple-text">White-labeling</h3>
                <button
                  onClick={() => setIsEditingTheme(!isEditingTheme)}
                  className="text-sm text-apple-blue hover:text-apple-blue-hover font-medium"
                >
                  {isEditingTheme ? "Done" : "Edit"}
                </button>
              </div>

              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-apple-secondary mb-2">
                    Client Logo
                  </label>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-apple-bg flex items-center justify-center text-xl border border-apple-border">
                      {activeTenant.logo}
                    </div>
                    {isEditingTheme && (
                      <input
                        type="text"
                        className="w-20 text-center"
                        value={activeTenant.logo}
                        onChange={(e) =>
                          setActiveTenant({ ...activeTenant, logo: e.target.value })
                        }
                      />
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-apple-secondary mb-2">
                    Brand Color Theme
                  </label>
                  <div className="flex gap-3">
                    {["blue", "green", "purple", "orange", "red"].map((color) => (
                      <button
                        key={color}
                        disabled={!isEditingTheme}
                        onClick={() => setActiveTenant({ ...activeTenant, theme: color })}
                        className={`w-8 h-8 rounded-full transition-transform ${
                          activeTenant.theme === color
                            ? "ring-2 ring-offset-2 ring-apple-text scale-110"
                            : "opacity-50 hover:opacity-100"
                        } ${!isEditingTheme && "cursor-default"}`}
                        style={{
                          backgroundColor:
                            color === "blue" ? "#0071e3" :
                            color === "green" ? "#34c759" :
                            color === "purple" ? "#af52de" :
                            color === "orange" ? "#ff9500" : "#ff3b30",
                        }}
                      />
                    ))}
                  </div>
                </div>

                {isEditingTheme && (
                  <div className="pt-4 border-t border-apple-border/50">
                    <button className="w-full py-2.5 rounded-apple-sm bg-apple-text text-white text-sm font-medium hover:bg-black transition-colors">
                      Save Changes
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
