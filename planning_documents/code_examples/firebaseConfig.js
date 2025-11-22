// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "AIzaSyAep5gnbVGt-_tR4IMGOS3hEI1pShEEXo4",
    authDomain: "polyglot-forms-919f2.firebaseapp.com",
    projectId: "polyglot-forms-919f2",
    storageBucket: "polyglot-forms-919f2.firebasestorage.app",
    messagingSenderId: "582198980936",
    appId: "1:582198980936:web:a31050cbb819882286437d",
    measurementId: "G-ET06LQBRJ1"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);