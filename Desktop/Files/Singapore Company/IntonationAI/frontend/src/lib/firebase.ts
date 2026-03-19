import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
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

function getFirebaseApp(): FirebaseApp | null {
  const key = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!key || !projectId) return null;
  if (getApps().length === 0) {
    return initializeApp({
      apiKey: key,
      projectId,
      authDomain: `${projectId}.firebaseapp.com`,
    });
  }
  return getApps()[0] as FirebaseApp;
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
  if (!key || !projectId) return null;
  try {
    const app: FirebaseApp =
      getApps().length === 0
        ? initializeApp({
            apiKey: key,
            projectId,
            authDomain: `${projectId}.firebaseapp.com`,
          })
        : (getApps()[0] as FirebaseApp);
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
