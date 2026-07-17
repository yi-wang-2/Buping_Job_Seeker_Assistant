import App from "./App";
import AuthGate from "./components/AuthGate";

export default function CloudApp() {
  return (
    <AuthGate>
      <App />
    </AuthGate>
  );
}
