// This service worker receives push notifications even when the app
// (browser tab) is closed. It runs in the background.

importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");

// ⚠️ Replace with YOUR OWN Firebase project config (from Firebase Console
// -> Project Settings -> General -> Your apps -> Web app).
// This config is safe to be public - it is not a secret.
firebase.initializeApp({
  apiKey: "REPLACE_ME",
  authDomain: "REPLACE_ME.firebaseapp.com",
  projectId: "REPLACE_ME",
  storageBucket: "REPLACE_ME.appspot.com",
  messagingSenderId: "REPLACE_ME",
  appId: "REPLACE_ME"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = payload.notification?.title || "Breakout Alert";
  const options = {
    body: payload.notification?.body || "",
    icon: "icon-192.png",
    badge: "icon-192.png",
    data: payload.data || {}
  };
  self.registration.showNotification(title, options);
});
