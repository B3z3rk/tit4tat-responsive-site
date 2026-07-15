(function () {
  const api = window.Tit4TatAPI;

  // Auth now lives server-side (real password hashing, a real session cookie,
  // and a real member-approval workflow) instead of localStorage. These
  // functions keep their old names/signatures so every page that already
  // calls window.Tit4TatDB.* needs only to await them.

  async function authenticateUser(email, password) {
    return api.login(email, password);
  }

  async function registerUser(profile) {
    const formData = new FormData();
    formData.append("name", profile.name);
    formData.append("email", profile.email);
    if (profile.password) formData.append("password", profile.password);
    if (profile.phone) formData.append("phone", profile.phone);
    if (profile.communityArea) formData.append("communityArea", profile.communityArea);
    if (profile.referenceName) formData.append("referenceName", profile.referenceName);
    if (profile.referenceUserId) formData.append("referenceUserId", profile.referenceUserId);
    if (profile.referenceFile) formData.append("referenceFile", profile.referenceFile);
    if (profile.idFile) formData.append("idFile", profile.idFile);
    if (profile.billFile) formData.append("billFile", profile.billFile);
    return api.register(formData);
  }

  async function getCurrentUser() {
    try {
      return await api.getMe();
    } catch (err) {
      return null;
    }
  }

  async function signOut() {
    try {
      await api.logout();
    } catch (err) {
      // ignore - we're leaving the session either way
    }
    window.location.href = "sects.html";
  }

  function getRoleLabel(role) {
    switch (role) {
      case "SUPER_ADMIN":       return "Super Admin";
      case "HOA":               return "HOA";
      case "MEMBER":            return "Verified Member";
      case "LOCAL_BUSINESS":    return "Local Business";
      case "COMMUNITY_LEADER":  return "Community Leader";
      case "EMERGENCY_CONTACT": return "Emergency Contact";
      case "REGULAR_MEMBER":    return "Community Member";
      default:                  return "Member";
    }
  }

  function getRoleBadge(role) {
    switch (role) {
      case "SUPER_ADMIN":       return { label: "Super Admin",       color: "#991b1b", bg: "#fee2e2" };
      case "HOA":               return { label: "HOA",               color: "#1e3a5f", bg: "#e7edf3" };
      case "MEMBER":            return { label: "Verified Member",  color: "#166534", bg: "#dcfce7" };
      case "LOCAL_BUSINESS":    return { label: "Local Business",   color: "#92400e", bg: "#fef3c7" };
      case "COMMUNITY_LEADER":  return { label: "Community Leader", color: "#1e3a5f", bg: "#e7edf3" };
      case "EMERGENCY_CONTACT": return { label: "Emergency Contact",color: "#991b1b", bg: "#fee2e2" };
      case "REGULAR_MEMBER":    return { label: "Community Member", color: "#92400e", bg: "#fef3c7" };
      default:                  return { label: "Member",           color: "#1e3a5f", bg: "#e7edf3" };
    }
  }

  function hasAccess(user, requiredRole) {
    const roleOrder = {
      SUPER_ADMIN: 4, HOA: 3,
      MEMBER: 2, LOCAL_BUSINESS: 2, COMMUNITY_LEADER: 2, EMERGENCY_CONTACT: 2,
      REGULAR_MEMBER: 1,
    };
    return user && roleOrder[user.role] >= roleOrder[requiredRole];
  }

  // Renders a real uploaded photo (if the user has one) into an avatar
  // container, falling back to the existing initials-circle look otherwise.
  // Works for any element already styled like `.avatar`/`.member-avatar`
  // (a fixed-size box with a border-radius) since the <img> just fills it.
  function renderAvatar(elementId, user) {
    const el = document.getElementById(elementId);
    if (!el) return;

    if (user && user.avatarUrl) {
      el.innerHTML = `<img src="${user.avatarUrl}" alt="${(user.name || "User").replace(/"/g, "&quot;")}" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;" />`;
    } else {
      el.textContent = (user && user.name ? user.name : "U").charAt(0).toUpperCase();
    }
  }

  function getMenuItems(user, currentPage) {
    const role = user && user.role ? user.role : "REGULAR_MEMBER";
    const items = [];

    if (role === "HOA" || role === "SUPER_ADMIN") {
      // HOA and Super Admin share the same nav — Super Admin's extra powers
      // (managing other HOA accounts, viewing verification documents) live
      // inside the existing Settings/Dashboard pages rather than a separate
      // section. HOA gets its own dashboard (overview + approvals + emergency
      // log) rather than landing on the member activity dashboard;
      // Reports/Activities/Directory stay shared views since HOA's oversight
      // controls already live on them.
      items.push({ label: "Dashboard",      href: "sectadmin.html", key: "dashboard" });
      items.push({ label: "Reports",        href: "sectb.html",     key: "reports" });
      items.push({ label: "Activities",     href: "secta.html",     key: "activities" });
      items.push({ label: "Directory",      href: "sectc.html",     key: "directory" });
      items.push({ label: "Messages",       href: "sectmessages.html", key: "messages" });
      items.push({ label: "Announcements",  href: "sectadmin.html", key: "announcements" });
      items.push({ label: "Settings",       href: "sectsettings.html", key: "settings" });
    } else if (role === "MEMBER" || role === "LOCAL_BUSINESS" || role === "COMMUNITY_LEADER" || role === "EMERGENCY_CONTACT") {
      // Standard verified member access per role spec — Local Business/Community
      // Leader/Emergency Contact are specializations of the same member tier and
      // share this nav. Activities doubles as the dashboard (it has the "My
      // Activity" stats panel), so there's no separate Dashboard entry.
      items.push({ label: "Activities",  href: "secta.html", key: "activities" });
      items.push({ label: "Reports",     href: "sectb.html", key: "reports" });
      items.push({ label: "Directory",   href: "sectc.html", key: "directory" });
      items.push({ label: "Messages",    href: "sectmessages.html", key: "messages" });
      items.push({ label: "Tap Call",    href: "sectd.html", key: "emergency" });
      items.push({ label: "Emergency",   href: "sectd.html", key: "emergency" });
      items.push({ label: "My Business", href: "sectbusiness.html", key: "business" });
      items.push({ label: "Profile",     href: "sectprofile.html", key: "profile" });
    } else {
      // Basic verified access (REGULAR_MEMBER) per role spec. Activities
      // doubles as the dashboard here too, so no separate Dashboard entry.
      items.push({ label: "Activities", href: "secta.html", key: "activities" });
      items.push({ label: "Reports",    href: "sectb.html", key: "reports" });
      items.push({ label: "Directory",  href: "sectc.html", key: "directory" });
      items.push({ label: "Messages",   href: "sectmessages.html", key: "messages" });
      items.push({ label: "Emergency",  href: "sectd.html", key: "emergency" });
      items.push({ label: "Profile",    href: "sectprofile.html", key: "profile" });
    }

    return items.map(item => ({ ...item, active: item.key === currentPage }));
  }

  function renderMenu(containerId, currentPage, user) {
    const container = document.getElementById(containerId);
    if (!container) {
      return;
    }

    const items = getMenuItems(user, currentPage);
    container.innerHTML = items.map(item => {
      const activeClass = item.active ? "active" : "";
      if (item.key === "admin") {
        return `<a href="#" class="${activeClass}" onclick="event.preventDefault(); window.Tit4TatDB.handleMenuAction('admin')">${item.label}</a>`;
      }
      return `<a href="${item.href}" class="${activeClass}">${item.label}</a>`;
    }).join("");

    // Inject role chip above the nav if container has a sibling #roleBadge
    const badgeEl = document.getElementById("roleBadge");
    if (badgeEl && user) {
      const b = getRoleBadge(user.role);
      badgeEl.innerHTML = `<span style="display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;font-size:0.72rem;font-weight:700;background:${b.bg};color:${b.color};">${b.label}</span>`;
    }

    // Append sign-out below the nav if a sign-out container exists
    const signoutEl = document.getElementById("sidebarSignout");
    if (signoutEl) {
      signoutEl.innerHTML = `<a href="#" onclick="event.preventDefault(); window.Tit4TatDB.signOut()">🚪 Sign Out</a>`;
    }
  }

  // Fixed bottom Message / Report / Call quick-action bar shown on phones
  // for Member and Regular Member roles (Admin keeps the hamburger nav only,
  // since their toolset doesn't fit a 3-icon bar).
  function renderMobileActionBar(containerId, user) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const role = user && user.role;
    if (role !== "MEMBER" && role !== "REGULAR_MEMBER") {
      container.classList.remove("has-actions");
      container.innerHTML = "";
      document.body.classList.remove("has-mobile-actions");
      return;
    }

    container.classList.add("has-actions");
    container.innerHTML = `
      <a href="sectmessages.html"><span class="mab-icon">💬</span>Message</a>
      <a href="sectb.html" class="mab-emergency"><span class="mab-icon">🚨</span>Report</a>
      <a href="sectd.html"><span class="mab-icon">📞</span>Call</a>
    `;
    document.body.classList.add("has-mobile-actions");
  }

  async function handleMenuAction(action) {
    if (action === "admin") {
      const user = await getCurrentUser();
      const message = hasAccess(user, "HOA")
        ? "HOA controls are ready for administrators."
        : "This action requires HOA access.";

      if (window.showToast) {
        window.showToast(message);
      } else {
        alert(message);
      }
    }
  }

  // Community-wide emergency alerts: polls for calls made by anyone else and
  // surfaces each one as a persistent banner (its own container, appended to
  // <body> the first time it's needed) that stays on screen until the member
  // closes it, rather than a page's own auto-dismissing showToast.
  let emergencyAlertLastId = 0;
  let emergencyAlertTimer = null;
  let emergencyAlertPrimed = false;

  function getEmergencyBannerContainer() {
    let container = document.getElementById("t4t-emergency-banners");
    if (!container) {
      container = document.createElement("div");
      container.id = "t4t-emergency-banners";
      container.className = "t4t-emergency-banners";
      document.body.appendChild(container);
    }
    return container;
  }

  function showEmergencyBanner(alert) {
    const container = getEmergencyBannerContainer();

    const banner = document.createElement("div");
    banner.className = "t4t-emergency-banner";

    const icon = document.createElement("span");
    icon.className = "t4t-emergency-banner-icon";
    icon.textContent = "🚨";

    const body = document.createElement("span");
    body.className = "t4t-emergency-banner-body";

    const text = document.createElement("span");
    text.className = "t4t-emergency-banner-message";
    text.textContent = `${alert.callerName} raised an emergency alert.`;
    body.appendChild(text);

    if (alert.callerLocation) {
      const location = document.createElement("span");
      location.className = "t4t-emergency-banner-location";
      location.textContent = `📍 ${alert.callerLocation}`;
      body.appendChild(location);
    }

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "t4t-emergency-banner-close";
    closeBtn.setAttribute("aria-label", "Close alert");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", () => banner.remove());

    banner.append(icon, body, closeBtn);
    container.appendChild(banner);
  }

  function startEmergencyAlertPolling() {
    if (emergencyAlertTimer) {
      return;
    }

    async function poll() {
      let alerts;
      try {
        alerts = await api.getEmergencyAlerts(emergencyAlertLastId);
      } catch (err) {
        return;
      }

      if (!alerts.length) {
        return;
      }

      const highestId = alerts.reduce((max, item) => Math.max(max, item.id), emergencyAlertLastId);
      emergencyAlertLastId = highestId;

      // The very first poll just establishes the baseline (everything already on
      // record) so a fresh page load doesn't replay every past emergency call.
      if (!emergencyAlertPrimed) {
        emergencyAlertPrimed = true;
        return;
      }

      alerts.forEach(item => showEmergencyBanner(item));
    }

    poll();
    emergencyAlertTimer = setInterval(poll, 6000);
  }

  window.Tit4TatDB = {
    authenticateUser,
    registerUser,
    getCurrentUser,
    getRoleLabel,
    getRoleBadge,
    hasAccess,
    renderAvatar,
    getMenuItems,
    renderMenu,
    renderMobileActionBar,
    handleMenuAction,
    signOut,
    startEmergencyAlertPolling
  };
})();
