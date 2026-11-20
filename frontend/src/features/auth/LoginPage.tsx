import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../../services/api/authService";
import { useUser } from "../../context/UserContext";
import logo from "../../assets/jusr-logo-transparent.png";
import "../landing/landing.css";

function LoginPage() {
  const navigate = useNavigate();
  const { loginUser } = useUser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login(email.trim(), password);
      loginUser(user);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <Link to="/" aria-label="Back to Jusr AI home">
          <img className="login-brand" src={logo} alt="Jusr AI" />
        </Link>
        <h1>Welcome to Jusr AI</h1>
        <p className="login-subtitle">Sign in to continue to your workspace.</p>

        <label className="login-field" htmlFor="email">
          <span>Email address</span>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="username"
            placeholder="Enter your email"
          />
        </label>

        <label className="login-field" htmlFor="password">
          <span>Password</span>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            placeholder="Enter your password"
          />
        </label>

        {error && <p className="login-error" role="alert">{error}</p>}

        <button className="login-submit" type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
        <p className="login-footer">
          Need workspace access? <Link to="/request-access">Learn how to request it</Link>
        </p>
      </form>
    </main>
  );
}

export default LoginPage;
