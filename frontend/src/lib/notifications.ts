interface InvitePayload {
  company_name: string;
  inviter_name: string;
  invitee_name: string;
  invitee_email: string;
  role: string;
}

interface WelcomePayload {
  company_name: string;
  admin_name: string;
  admin_email: string;
}

async function postNotification(path: string, payload: InvitePayload | WelcomePayload): Promise<void> {
  const response = await fetch(`/api/notifications/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.ok) return;

  let detail = "Nao foi possivel enviar e-mail.";
  try {
    const data = (await response.json()) as { detail?: string };
    if (typeof data.detail === "string" && data.detail.trim()) {
      detail = data.detail;
    }
  } catch {
    // keep default message
  }

  throw new Error(detail);
}

export async function sendUserInviteEmail(payload: InvitePayload): Promise<void> {
  await postNotification("invite-user", payload);
}

export async function sendAdminWelcomeEmail(payload: WelcomePayload): Promise<void> {
  await postNotification("admin-welcome", payload);
}
