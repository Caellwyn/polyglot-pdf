// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "REDACTED_FIREBASE_API_KEY",
    authDomain: "polyglot-forms-919f2.firebaseapp.com",
    projectId: "polyglot-forms-919f2",
    storageBucket: "polyglot-forms-919f2.firebasestorage.app",
    messagingSenderId: "REDACTED_MESSAGING_ID",
    appId: "1:REDACTED_MESSAGING_ID:web:a31050cbb819882286437d",
    measurementId: "G-ET06LQBRJ1"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);