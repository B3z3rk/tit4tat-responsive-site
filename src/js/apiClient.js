(function () {
  class ApiError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status;
    }
  }

  async function request(method, path, body) {
    const res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const errBody = await res.json();
        detail = errBody.detail || detail;
      } catch (_) {
        // no JSON body on this error response
      }
      throw new ApiError(res.status, detail);
    }

    if (res.status === 204) {
      return null;
    }
    return res.json();
  }

  // Like request(), but sends a FormData body (multipart/form-data) instead
  // of JSON — used for registration, which includes file uploads. Never set
  // Content-Type manually here: the browser fills in the multipart boundary.
  async function requestMultipart(method, path, formData) {
    const res = await fetch(path, { method, credentials: "same-origin", body: formData });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const errBody = await res.json();
        detail = errBody.detail || detail;
      } catch (_) {
        // no JSON body on this error response
      }
      throw new ApiError(res.status, detail);
    }

    return res.json();
  }

  window.Tit4TatAPI = {
    ApiError,

    // auth
    getMe() {
      return request("GET", "/api/auth/me");
    },
    login(email, password) {
      return request("POST", "/api/auth/login", { email, password });
    },
    verifyMfaEnroll(challengeToken, code) {
      return request("POST", "/api/auth/mfa/verify-enroll", { challengeToken, code });
    },
    verifyMfaLogin(challengeToken, code) {
      return request("POST", "/api/auth/mfa/verify-login", { challengeToken, code });
    },
    register(formData) {
      return requestMultipart("POST", "/api/auth/register", formData);
    },
    logout() {
      return request("POST", "/api/auth/logout");
    },
    changePassword(currentPassword, newPassword) {
      return request("POST", "/api/auth/change-password", { currentPassword, newPassword });
    },

    // admin
    getAdminOverview() {
      return request("GET", "/api/admin/overview");
    },
    getPendingUsers() {
      return request("GET", "/api/admin/users/pending");
    },
    approveUser(id, role) {
      return request("POST", `/api/admin/users/${id}/approve`, { role });
    },
    rejectUser(id, reason) {
      return request("POST", `/api/admin/users/${id}/reject`, { reason });
    },
    getAdminUsers() {
      return request("GET", "/api/admin/users");
    },
    resetUserPassword(id, newPassword) {
      return request("POST", `/api/admin/users/${id}/reset-password`, { newPassword: newPassword || null });
    },
    changeUserRole(id, role) {
      return request("POST", `/api/admin/users/${id}/role`, { role });
    },
    suspendUser(id) {
      return request("POST", `/api/admin/users/${id}/suspend`);
    },
    reactivateUser(id) {
      return request("POST", `/api/admin/users/${id}/reactivate`);
    },
    getAuditLog() {
      return request("GET", "/api/admin/audit-log");
    },

    // activities
    getActivities() {
      return request("GET", "/api/activities");
    },
    joinActivity(id) {
      return request("POST", `/api/activities/${id}/join`);
    },
    createActivity(payload) {
      return request("POST", "/api/activities", payload);
    },
    deleteActivity(id) {
      return request("DELETE", `/api/activities/${id}`);
    },
    async uploadActivityCover(id, file) {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`/api/activities/${id}/cover`, {
        method: "POST",
        credentials: "same-origin",
        body: formData
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const errBody = await res.json();
          detail = errBody.detail || detail;
        } catch (_) {
          // no JSON body on this error response
        }
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },

    // reports
    getReportCategories() {
      return request("GET", "/api/report-categories");
    },
    getReports() {
      return request("GET", "/api/reports");
    },
    createReport(payload) {
      return request("POST", "/api/reports", payload);
    },
    updateReportStatus(id, status) {
      return request("PATCH", `/api/reports/${id}/status`, { status });
    },

    // directory
    getMembers() {
      return request("GET", "/api/members");
    },
    getMember(id) {
      return request("GET", `/api/members/${id}`);
    },
    getMyProfile() {
      return request("GET", "/api/members/me");
    },
    updateMyBusiness(payload) {
      return request("PATCH", "/api/members/me", payload);
    },
    updateMyProfileFields(payload) {
      return request("PATCH", "/api/members/me/profile", payload);
    },
    async uploadMyAvatar(file) {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/members/me/avatar", {
        method: "POST",
        credentials: "same-origin",
        body: formData
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const errBody = await res.json();
          detail = errBody.detail || detail;
        } catch (_) {
          // no JSON body on this error response
        }
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },

    // dashboard
    getMyStats() {
      return request("GET", "/api/dashboard/me");
    },

    // messages
    getContacts() {
      return request("GET", "/api/messages/contacts");
    },
    getThread(otherId, afterId) {
      const query = afterId ? `?after_id=${afterId}` : "";
      return request("GET", `/api/messages/${otherId}${query}`);
    },
    sendMessage(otherId, text) {
      return request("POST", `/api/messages/${otherId}`, { text });
    },

    // emergency
    getEmergencyTargets() {
      return request("GET", "/api/emergency/targets");
    },
    logEmergencyCall(targetType, targetLabel) {
      return request("POST", "/api/emergency/calls", { targetType, targetLabel });
    },
    getEmergencyLogs() {
      return request("GET", "/api/emergency/admin/calls");
    },
    getEmergencyAlerts(afterId) {
      const query = afterId ? `?after_id=${afterId}` : "";
      return request("GET", `/api/emergency/alerts${query}`);
    },

    // announcements
    getAnnouncements() {
      return request("GET", "/api/announcements");
    },
    createAnnouncement(payload) {
      return request("POST", "/api/announcements", payload);
    },
    deleteAnnouncement(id) {
      return request("DELETE", `/api/announcements/${id}`);
    }
  };
})();
