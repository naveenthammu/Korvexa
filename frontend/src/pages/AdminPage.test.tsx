import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminPage from "./AdminPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;

function findButton(container: HTMLElement, label: string) {
  return Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent?.includes(label)
  );
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function tokenForUser(userId: string) {
  return `header.${btoa(JSON.stringify({ sub: userId, role: "tenant_owner", tenant_id: "tenant-1" }))}.sig`;
}

afterEach(() => {
  if (root) {
    act(() => root?.unmount());
    root = null;
  }
  document.body.innerHTML = "";
});

describe("AdminPage store management", () => {
  it("deletes a store after confirmation", async () => {
    const apiRequest = vi.fn().mockResolvedValue({ success: true });
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[
            { id: "branch-1", name: "Main Store", address: "MG Road", phone: "9999999999", status: "active" },
            { id: "branch-2", name: "Second Store", status: "active" },
          ]}
          users={[]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    const deleteButton = findButton(container, "Delete");
    expect(deleteButton).toBeTruthy();

    await act(async () => {
      deleteButton?.click();
    });

    const confirmButton = findButton(container, "Confirm");
    expect(confirmButton).toBeTruthy();

    await act(async () => {
      confirmButton?.click();
    });

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/branches/branch-1", { method: "DELETE", token: "token" });
    expect(showToast).toHaveBeenCalledWith("Store Main Store deleted successfully!", "success");
    expect(onRefresh).toHaveBeenCalled();
  });
});

describe("AdminPage user lock controls", () => {
  it("unlocks a locked user through the unlock endpoint", async () => {
    const apiRequest = vi.fn().mockResolvedValue({ success: true });
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[
            {
              id: "user-1",
              name: "Locked Cashier",
              email: "locked@example.com",
              role: "cashier",
              branch_id: "branch-1",
              status: "active",
              locked: true,
            },
          ]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    const unlockButton = findButton(container, "Unlock");
    expect(unlockButton).toBeTruthy();

    await act(async () => {
      unlockButton?.click();
    });

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/admin/users/user-1/unlock", { method: "POST", token: "token" });
    expect(showToast).toHaveBeenCalledWith("User Locked Cashier unlocked", "success");
    expect(onRefresh).toHaveBeenCalled();
  });
});

describe("AdminPage user creation errors", () => {
  it("shows the backend reason when user creation fails", async () => {
    const apiRequest = vi
      .fn()
      .mockRejectedValue(new Error(JSON.stringify({ message: "Managers cannot create or manage manager accounts" })));
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    await act(async () => {
      findButton(container, "New User")?.click();
    });

    const modalInputs = Array.from(container.querySelectorAll(".modal-box input")) as HTMLInputElement[];
    setInputValue(modalInputs[0], "New User");
    setInputValue(container.querySelector(".modal-box input[type='email']") as HTMLInputElement, "new.user@example.com");
    setInputValue(container.querySelector(".modal-box input[type='password']") as HTMLInputElement, "ChangeMe123!");

    await act(async () => {
      (container.querySelector(".modal-box form") as HTMLFormElement).dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true })
      );
    });

    expect(showToast).toHaveBeenCalledWith("Managers cannot create or manage manager accounts", "error");
  });
});

describe("AdminPage user creation permissions", () => {
  it("sends selected individual permissions when creating a user", async () => {
    const apiRequest = vi.fn().mockResolvedValue({ success: true });
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    await act(async () => {
      findButton(container, "New User")?.click();
    });

    const nameInput = container.querySelector(".modal-box input") as HTMLInputElement;
    const emailInput = container.querySelector(".modal-box input[type='email']") as HTMLInputElement;
    const passwordInput = container.querySelector(".modal-box input[type='password']") as HTMLInputElement;
    const viewStaffPermission = Array.from(container.querySelectorAll(".modal-box label")).find((label) =>
      label.textContent?.includes("View Staff")
    );
    const permissionCheckbox = viewStaffPermission?.querySelector("input") as HTMLInputElement;

    await act(async () => {
      setInputValue(nameInput, "Permissioned Cashier");
      setInputValue(emailInput, "permissioned.cashier@example.com");
      setInputValue(passwordInput, "ChangeMe123!");
      permissionCheckbox.click();
    });

    await act(async () => {
      (container.querySelector(".modal-box form") as HTMLFormElement).dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true })
      );
    });

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/users", {
      method: "POST",
      token: "token",
      body: JSON.stringify({
        name: "Permissioned Cashier",
        email: "permissioned.cashier@example.com",
        phone: "",
        password: "ChangeMe123!",
        role: "manager",
        branch_id: "branch-1",
        permissions: ["employee:view"],
      }),
    });
  });
});

describe("AdminPage user status controls", () => {
  it("enables an inactive user through the status endpoint", async () => {
    const apiRequest = vi.fn().mockResolvedValue({ success: true });
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[
            {
              id: "user-1",
              name: "Inactive Cashier",
              email: "inactive@example.com",
              role: "cashier",
              branch_id: "branch-1",
              status: "inactive",
              locked: false,
            },
          ]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    const enableButton = findButton(container, "Enable");
    expect(enableButton).toBeTruthy();

    await act(async () => {
      enableButton?.click();
    });

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/users/user-1", {
      method: "PATCH",
      token: "token",
      body: JSON.stringify({ status: "active" }),
    });
    expect(showToast).toHaveBeenCalledWith("User Inactive Cashier enabled", "success");
    expect(onRefresh).toHaveBeenCalled();
  });

  it("does not show lock, disable, or delete actions for the signed-in user", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token={tokenForUser("user-self")}
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[
            {
              id: "user-self",
              name: "Current Admin",
              email: "current@example.com",
              role: "tenant_owner",
              branch_id: "branch-1",
              status: "active",
              locked: false,
            },
          ]}
          onRefresh={vi.fn()}
          showToast={vi.fn()}
          apiRequest={vi.fn().mockResolvedValue({ success: true })}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    expect(findButton(container, "Lock")).toBeUndefined();
    expect(findButton(container, "Disable")).toBeUndefined();
    expect(findButton(container, "Delete")).toBeUndefined();
    expect(container.textContent).toContain("Current user");
  });
});

describe("AdminPage password reset errors", () => {
  it("shows backend password reset errors and keeps the modal open", async () => {
    const apiRequest = vi.fn().mockRejectedValue(new Error(JSON.stringify({ detail: "Password must be at least 12 characters" })));
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[
            {
              id: "user-1",
              name: "Reset Cashier",
              email: "reset@example.com",
              role: "cashier",
              branch_id: "branch-1",
              status: "active",
              locked: false,
            },
          ]}
          onRefresh={vi.fn()}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Users")?.click();
    });

    await act(async () => {
      findButton(container, "Reset PW")?.click();
    });

    const passwordInput = container.querySelector(".modal-box input[type='password']") as HTMLInputElement;
    await act(async () => {
      setInputValue(passwordInput, "short");
    });

    await act(async () => {
      (container.querySelector(".modal-box form") as HTMLFormElement).dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true })
      );
    });

    expect(showToast).toHaveBeenCalledWith("Password must be at least 12 characters", "error");
    expect(container.textContent).toContain("Reset Password for Reset Cashier");
  });
});

describe("AdminPage role and policy settings", () => {
  it("loads saved role permissions and saves backend permission codes", async () => {
    const apiRequest = vi.fn((url: string, opts?: { method?: string }) => {
      if (url === "/api/v1/admin/permissions" && !opts?.method) {
        return Promise.resolve({
          data: {
            role_permissions: {
              manager: ["user:manage"],
              cashier: ["payment:manage"],
              waiter: [],
              kitchen_staff: [],
              accountant: [],
            },
          },
        });
      }
      return Promise.resolve({ success: true });
    });
    const onRefresh = vi.fn();
    const showToast = vi.fn();
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[]}
          onRefresh={onRefresh}
          showToast={showToast}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Roles & Permissions")?.click();
    });

    expect(apiRequest).toHaveBeenCalledWith("/api/v1/admin/permissions", { token: "token" });

    await act(async () => {
      findButton(container, "Save Permissions")?.click();
    });

    expect(apiRequest).toHaveBeenLastCalledWith("/api/v1/admin/permissions", {
      method: "PATCH",
      token: "token",
      body: JSON.stringify({
        manager: ["user:manage"],
        cashier: ["payment:manage"],
        waiter: [],
        kitchen_staff: [],
        accountant: [],
      }),
    });
  });

  it("loads saved security policy values into the form", async () => {
    const apiRequest = vi.fn((url: string) => {
      if (url === "/api/v1/admin/security-settings") {
        return Promise.resolve({
          data: {
            password_min_length: 12,
            session_timeout_minutes: 45,
            multi_device_login: false,
            two_factor_auth: true,
            login_attempts_threshold: 4,
          },
        });
      }
      return Promise.resolve({ success: true });
    });
    const container = document.createElement("div");
    document.body.appendChild(container);

    await act(async () => {
      root = createRoot(container);
      root.render(
        <AdminPage
          token="token"
          userRole="tenant_owner"
          branches={[{ id: "branch-1", name: "Main Store", status: "active" }]}
          users={[]}
          onRefresh={vi.fn()}
          showToast={vi.fn()}
          apiRequest={apiRequest}
        />
      );
    });

    await act(async () => {
      findButton(container, "Security Policy")?.click();
    });

    const inputs = Array.from(container.querySelectorAll("input[type='number']")) as HTMLInputElement[];
    expect(inputs.map((input) => input.value)).toEqual(["12", "45", "4"]);
  });
});
