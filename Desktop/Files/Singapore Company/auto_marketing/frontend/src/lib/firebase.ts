import { getApps, initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const hasFirebaseConfig = Boolean(
  firebaseConfig.apiKey &&
    firebaseConfig.authDomain &&
    firebaseConfig.projectId &&
    firebaseConfig.appId,
);

const app =
  typeof window !== "undefined" && hasFirebaseConfig
    ? getApps().length === 0
      ? initializeApp(firebaseConfig)
      : getApps()[0]
    : null;

export const auth = app ? getAuth(app) : null;

const googleProvider = new GoogleAuthProvider();

export async function signInWithGoogle() {
  if (!auth) throw new Error("Firebase not configured");
  return signInWithPopup(auth, googleProvider);
}

export async function signInWithEmail(email: string, password: string) {
  if (!auth) throw new Error("Firebase not configured");
  return signInWithEmailAndPassword(auth, email, password);
}

export async function signUpWithEmail(email: string, password: string) {
  if (!auth) throw new Error("Firebase not configured");
  return createUserWithEmailAndPassword(auth, email, password);
}

export async function signOut() {
  if (!auth) return;
  return firebaseSignOut(auth);
}

export type { User };
