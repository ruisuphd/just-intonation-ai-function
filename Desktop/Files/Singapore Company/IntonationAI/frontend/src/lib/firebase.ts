import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getToken,
  initializeAppCheck,
  ReCaptchaV3Provider,
  type AppCheck,
} from "firebase/app-check";
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as fbSignOut,
  GoogleAuthProvider,
  signInWithPopup,
  onAuthStateChanged,
  type Auth,
  type User,
} from "firebase/auth";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";

let authInstance: Auth | null = null;
let appCheckInstance: AppCheck | null = null;

function ensureAppCheckInitialized(app: FirebaseApp): void {
  if (typeof window === "undefined") return;
  if (appCheckInstance) return;
  const siteKey = process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY?.trim();
  if (!siteKey) return;
  const debugToken = process.env.NEXT_PUBLIC_APP_CHECK_DEBUG_TOKEN?.trim();
  if (debugToken) {
    (
      globalThis as unknown as { FIREBASE_APPCHECK_DEBUG_TOKEN?: string }
    ).FIREBASE_APPCHECK_DEBUG_TOKEN = debugToken;
  }
  appCheckInstance = initializeAppCheck(app, {
    provider: new ReCaptchaV3Provider(siteKey),
    isTokenAutoRefreshEnabled: true,
  });
}

function getFirebaseApp(): FirebaseApp | null {
  const key = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!key || !projectId) {
    if (process.env.NODE_ENV === "production")
      throw new Error("NEXT_PUBLIC_FIREBASE_API_KEY and NEXT_PUBLIC_FIREBASE_PROJECT_ID are required for production.");
    return null;
  }
  if (getApps().length === 0) {
    const app = initializeApp({
      apiKey: key,
      projectId,
      authDomain: `${projectId}.firebaseapp.com`,
    });
    ensureAppCheckInitialized(app);
    return app;
  }
  const existing = getApps()[0] as FirebaseApp;
  ensureAppCheckInitialized(existing);
  return existing;
}

export function getFirestoreDb() {
  const app = getFirebaseApp();
  return app ? getFirestore(app) : null;
}

export function getFirebaseStorage() {
  const app = getFirebaseApp();
  return app ? getStorage(app) : null;
}

function initAuth(): Auth | null {
  if (authInstance !== null) return authInstance;
  const key = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!key || !projectId) {
    if (process.env.NODE_ENV === "production")
      throw new Error("NEXT_PUBLIC_FIREBASE_API_KEY and NEXT_PUBLIC_FIREBASE_PROJECT_ID are required for production.");
    return null;
  }
  try {
    const app: FirebaseApp =
      getApps().length === 0
        ? initializeApp({
            apiKey: key,
            projectId,
            authDomain: `${projectId}.firebaseapp.com`,
          })
        : (getApps()[0] as FirebaseApp);
    ensureAppCheckInitialized(app);
    authInstance = getAuth(app);
  } catch {
    return null;
  }
  return authInstance;
}

export const auth = new Proxy({} as Auth, {
  get(_, prop) {
    const a = initAuth();
    if (!a) return undefined;
    return (a as unknown as Record<string, unknown>)[prop as string];
  },
});

export async function signInEmail(email: string, password: string) {
  const a = initAuth();
  if (!a) throw new Error("Firebase not configured");
  return signInWithEmailAndPassword(a, email, password);
}

export async function signUpEmail(email: string, password: string) {
  const a = initAuth();
  if (!a) throw new Error("Firebase not configured");
  return createUserWithEmailAndPassword(a, email, password);
}

export async function signInGoogle() {
  const a = initAuth();
  if (!a) throw new Error("Firebase not configured");
  return signInWithPopup(a, new GoogleAuthProvider());
}

export async function signOut() {
  const a = initAuth();
  if (!a) return;
  return fbSignOut(a);
}

export function onAuthChange(cb: (user: User | null) => void) {
  const a = initAuth();
  if (!a) {
    cb(null);
    return () => {};
  }
  return onAuthStateChanged(a, cb);
}

export async function getIdToken(): Promise<string | null> {
  const a = initAuth();
  if (!a) return null;
  const user = a.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

/** Token for ``X-Firebase-AppCheck`` when App Check is initialized (requires ``NEXT_PUBLIC_RECAPTCHA_SITE_KEY``). */
export async function getAppCheckTokenForApi(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  getFirebaseApp();
  if (!appCheckInstance) return null;
  try {
    const { token } = await getToken(appCheckInstance, false);
    return token;
  } catch {
    return null;
  }
}
