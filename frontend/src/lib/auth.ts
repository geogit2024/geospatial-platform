export type CompanySegment =
  | "Agronegocio"
  | "Mineracao"
  | "Meio Ambiente"
  | "Engenharia e Infraestrutura"
  | "Geotecnologia (GIS)"
  | "Outro";

export type CompanySize = "Pequena" | "Media" | "Grande";
export type UserRole = "Admin" | "Editor" | "Leitor";
export type UserStatus = "ativo" | "pendente";

export interface CompanyProfile {
  name: string;
  segment: CompanySegment;
  size: CompanySize;
  country: string;
}

export interface UserProfile {
  name: string;
  email: string;
  password: string;
  role: UserRole;
  invitedAt: string;
}

export interface AccountStore {
  company: CompanyProfile;
  users: UserProfile[];
}

export interface SessionStore {
  email: string;
  startedAt: string;
}

interface RegistrationPayload {
  company: CompanyProfile;
  admin: Omit<UserProfile, "role" | "invitedAt">;
}

interface UpdateUserPayload {
  currentEmail: string;
  name: string;
  email: string;
  role: UserRole;
}

const ACCOUNT_KEY = "geopublish_accounts_v1";
const SESSION_KEY = "geopublish_session_v1";
const IMAGE_OWNERS_KEY = "geopublish_image_owners_v1";
const PENDING_PASSWORD_MARKER = "convite-pendente";
const SESSION_TTL_MS = 8 * 60 * 60 * 1000; // 8 hours
const PW_HASH_PREFIX = "sha256:";
const PW_SALT = "geopublish_pw_v1_";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

function isBrowser() {
  return typeof window !== "undefined";
}

function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

function readJson<T>(key: string): T | null {
  if (!isBrowser()) return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson<T>(key: string, value: T) {
  if (!isBrowser()) return;
  localStorage.setItem(key, JSON.stringify(value));
}

function writeAccount(account: AccountStore) {
  writeJson(ACCOUNT_KEY, account);
}

function getImageOwners(): Record<string, string> {
  return readJson<Record<string, string>>(IMAGE_OWNERS_KEY) ?? {};
}

function writeImageOwners(nextMap: Record<string, string>) {
  writeJson(IMAGE_OWNERS_KEY, nextMap);
}

function ensureAdminPresence(users: UserProfile[]): boolean {
  return users.some((user) => user.role === "Admin");
}

function updateSessionEmail(oldEmail: string, newEmail: string) {
  const current = getSession();
  if (!current) return;
  if (normalizeEmail(current.email) !== normalizeEmail(oldEmail)) return;
  writeJson(SESSION_KEY, { ...current, email: normalizeEmail(newEmail) });
}

async function hashPassword(password: string): Promise<string> {
  if (typeof crypto === "undefined" || !crypto.subtle) {
    return `plain:${btoa(password)}`;
  }
  const encoder = new TextEncoder();
  const data = encoder.encode(PW_SALT + password);
  const buffer = await crypto.subtle.digest("SHA-256", data);
  const hex = Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `${PW_HASH_PREFIX}${hex}`;
}

async function verifyPassword(input: string, stored: string): Promise<boolean> {
  if (stored === PENDING_PASSWORD_MARKER) return false;
  // Legacy plaintext — accept and will be upgraded on next save
  if (!stored.startsWith(PW_HASH_PREFIX) && !stored.startsWith("plain:")) {
    return stored === input;
  }
  if (stored.startsWith("plain:")) {
    return stored.slice(6) === btoa(input);
  }
  const hashed = await hashPassword(input);
  return hashed === stored;
}

export function getAccount(): AccountStore | null {
  return readJson<AccountStore>(ACCOUNT_KEY);
}

export function getSession(): SessionStore | null {
  return readJson<SessionStore>(SESSION_KEY);
}

export function isAuthenticated(): boolean {
  const session = getSession();
  if (!session) return false;
  const age = Date.now() - new Date(session.startedAt).getTime();
  if (age > SESSION_TTL_MS) {
    if (isBrowser()) localStorage.removeItem(SESSION_KEY);
    return false;
  }
  return true;
}

export async function registerCompanyAndAdmin(payload: RegistrationPayload): Promise<{
  ok: boolean;
  error?: string;
}> {
  const normalizedEmail = normalizeEmail(payload.admin.email);

  if (!EMAIL_REGEX.test(normalizedEmail)) {
    return { ok: false, error: "Informe um e-mail valido." };
  }

  if (!payload.admin.name.trim()) {
    return { ok: false, error: "Informe o nome do administrador." };
  }

  const hashedPassword = await hashPassword(payload.admin.password);

  const nextAccount: AccountStore = {
    company: payload.company,
    users: [
      {
        name: payload.admin.name.trim(),
        email: normalizedEmail,
        password: hashedPassword,
        role: "Admin",
        invitedAt: new Date().toISOString(),
      },
    ],
  };

  writeAccount(nextAccount);
  writeJson(SESSION_KEY, {
    email: normalizedEmail,
    startedAt: new Date().toISOString(),
  });

  return { ok: true };
}

export async function login(email: string, password: string): Promise<{ ok: boolean; error?: string }> {
  const account = getAccount();
  if (!account) {
    return { ok: false, error: "Nenhuma empresa cadastrada. Crie sua conta primeiro." };
  }

  const normalizedEmail = normalizeEmail(email);
  const user = account.users.find((item) => normalizeEmail(item.email) === normalizedEmail);

  if (!user) {
    return { ok: false, error: "Credenciais invalidas. Verifique e tente novamente." };
  }

  const match = await verifyPassword(password, user.password);
  if (!match) {
    return { ok: false, error: "Credenciais invalidas. Verifique e tente novamente." };
  }

  // Upgrade legacy plaintext password on successful login
  if (!user.password.startsWith(PW_HASH_PREFIX) && !user.password.startsWith("plain:")) {
    const upgraded = await hashPassword(password);
    const upgradedUsers = account.users.map((u) =>
      normalizeEmail(u.email) === normalizedEmail ? { ...u, password: upgraded } : u
    );
    writeAccount({ ...account, users: upgradedUsers });
  }

  writeJson(SESSION_KEY, {
    email: normalizedEmail,
    startedAt: new Date().toISOString(),
  });

  return { ok: true };
}

export function logout() {
  if (!isBrowser()) return;
  localStorage.removeItem(SESSION_KEY);
}

export function getCurrentUser(): UserProfile | null {
  const session = getSession();
  const account = getAccount();
  if (!session || !account) return null;
  return account.users.find((user) => normalizeEmail(user.email) === normalizeEmail(session.email)) ?? null;
}

export function canManageUsers(): boolean {
  const current = getCurrentUser();
  return current?.role === "Admin";
}

export function getUserStatus(user: UserProfile): UserStatus {
  return user.password === PENDING_PASSWORD_MARKER ? "pendente" : "ativo";
}

export function addInvitedUser(input: {
  name: string;
  email: string;
  role: UserRole;
  password?: string;
}): { ok: boolean; error?: string } {
  const account = getAccount();
  if (!account) return { ok: false, error: "Empresa nao encontrada." };

  const normalizedEmail = normalizeEmail(input.email);

  if (!EMAIL_REGEX.test(normalizedEmail)) {
    return { ok: false, error: "Informe um e-mail valido." };
  }

  if (account.users.some((user) => normalizeEmail(user.email) === normalizedEmail)) {
    return { ok: false, error: "Usuario ja cadastrado com este e-mail." };
  }

  const nextAccount: AccountStore = {
    ...account,
    users: [
      ...account.users,
      {
        name: input.name.trim(),
        email: normalizedEmail,
        password: input.password ?? PENDING_PASSWORD_MARKER,
        role: input.role,
        invitedAt: new Date().toISOString(),
      },
    ],
  };

  writeAccount(nextAccount);
  return { ok: true };
}

export function updateUserRole(email: string, role: UserRole): { ok: boolean; error?: string } {
  const account = getAccount();
  if (!account) return { ok: false, error: "Empresa nao encontrada." };

  const normalizedEmail = normalizeEmail(email);
  const users = [...account.users];
  const index = users.findIndex((user) => normalizeEmail(user.email) === normalizedEmail);
  if (index < 0) return { ok: false, error: "Usuario nao encontrado." };

  users[index] = { ...users[index], role };

  if (!ensureAdminPresence(users)) {
    return { ok: false, error: "A empresa precisa manter pelo menos um Admin." };
  }

  writeAccount({ ...account, users });
  return { ok: true };
}

export function updateUserProfile(payload: UpdateUserPayload): { ok: boolean; error?: string } {
  const account = getAccount();
  if (!account) return { ok: false, error: "Empresa nao encontrada." };

  const currentEmail = normalizeEmail(payload.currentEmail);
  const nextEmail = normalizeEmail(payload.email);
  const nextName = payload.name.trim();

  if (!nextName) return { ok: false, error: "Nome e obrigatorio." };

  if (!EMAIL_REGEX.test(nextEmail)) {
    return { ok: false, error: "Informe um e-mail valido." };
  }

  const users = [...account.users];
  const targetIndex = users.findIndex((user) => normalizeEmail(user.email) === currentEmail);
  if (targetIndex < 0) return { ok: false, error: "Usuario nao encontrado." };

  const duplicated = users.some(
    (user, index) => index !== targetIndex && normalizeEmail(user.email) === nextEmail
  );
  if (duplicated) return { ok: false, error: "Ja existe outro usuario com este e-mail." };

  users[targetIndex] = { ...users[targetIndex], name: nextName, email: nextEmail, role: payload.role };

  if (!ensureAdminPresence(users)) {
    return { ok: false, error: "A empresa precisa manter pelo menos um Admin." };
  }

  writeAccount({ ...account, users });
  updateSessionEmail(currentEmail, nextEmail);
  return { ok: true };
}

export function removeUser(email: string): { ok: boolean; error?: string } {
  const account = getAccount();
  if (!account) return { ok: false, error: "Empresa nao encontrada." };

  const targetEmail = normalizeEmail(email);
  const session = getSession();
  if (session && normalizeEmail(session.email) === targetEmail) {
    return { ok: false, error: "Nao e permitido remover o usuario logado." };
  }

  const users = account.users.filter((user) => normalizeEmail(user.email) !== targetEmail);
  if (users.length === account.users.length) {
    return { ok: false, error: "Usuario nao encontrado." };
  }

  if (!ensureAdminPresence(users)) {
    return { ok: false, error: "A empresa precisa manter pelo menos um Admin." };
  }

  writeAccount({ ...account, users });
  return { ok: true };
}

export async function resetUserPassword(email: string, newPassword: string): Promise<{ ok: boolean; error?: string }> {
  const account = getAccount();
  if (!account) return { ok: false, error: "Empresa nao encontrada." };

  const targetEmail = normalizeEmail(email);
  const users = [...account.users];
  const index = users.findIndex((user) => normalizeEmail(user.email) === targetEmail);
  if (index < 0) return { ok: false, error: "Usuario nao encontrado." };

  if (newPassword.trim().length < 8) {
    return { ok: false, error: "A nova senha deve ter no minimo 8 caracteres." };
  }

  users[index] = { ...users[index], password: await hashPassword(newPassword) };
  writeAccount({ ...account, users });
  return { ok: true };
}

export function getInvitedUsers(): UserProfile[] {
  const account = getAccount();
  if (!account) return [];
  return [...account.users].sort((a, b) => new Date(b.invitedAt).getTime() - new Date(a.invitedAt).getTime());
}

export function registerImageOwner(imageId: string, email?: string): void {
  if (!imageId.trim()) return;
  const ownerEmail = normalizeEmail(email ?? getCurrentUser()?.email ?? "");
  if (!ownerEmail) return;
  const owners = getImageOwners();
  owners[imageId] = ownerEmail;
  writeImageOwners(owners);
}

export function getImageOwner(imageId: string): string | null {
  if (!imageId.trim()) return null;
  const owners = getImageOwners();
  const owner = owners[imageId];
  return owner ? normalizeEmail(owner) : null;
}
