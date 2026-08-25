/**
 * Firebase (web) for the admin panel — Google Sign-In.
 * Config values are public client identifiers per Firebase docs.
 */
import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  type User,
} from 'firebase/auth'

const firebaseConfig = {
  apiKey: 'AIzaSyDlJ5R1s-mfF6924eA0N3qC3esxiNmfxgw',
  authDomain: 'bofedge-f72ae.firebaseapp.com',
  projectId: 'bofedge-f72ae',
  storageBucket: 'bofedge-f72ae.firebasestorage.app',
  messagingSenderId: '443524693149',
  appId: '1:443524693149:web:79622be6cb6f1429a8a874',
}

const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)

const googleProvider = new GoogleAuthProvider()

/** Popup-based Google Sign-In. Resolves with the signed-in Firebase user. */
export async function googleSignIn(): Promise<User> {
  const cred = await signInWithPopup(auth, googleProvider)
  return cred.user
}

/** Fresh (auto-refreshing) ID token for API calls, or null when signed out. */
export async function currentIdToken(): Promise<string | null> {
  const user = auth.currentUser
  if (!user) return null
  try {
    return await user.getIdToken()
  } catch {
    return null
  }
}

/** Subscribe to Firebase session changes; returns unsubscribe fn. */
export function watchAuth(cb: (user: User | null) => void): () => void {
  return onAuthStateChanged(auth, cb)
}

export async function firebaseSignOut(): Promise<void> {
  await signOut(auth).catch(() => undefined)
}
