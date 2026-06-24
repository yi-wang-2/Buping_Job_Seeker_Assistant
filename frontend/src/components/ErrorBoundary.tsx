import { Component, type ReactNode, type ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Generic React Error Boundary. Catches uncaught render-time errors
 * anywhere in the subtree and shows a useful message instead of
 * letting the whole page go blank.
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log to console for developer debugging
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] Caught error:", error, info);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleReset);
      }
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-8 dark:bg-gray-900">
          <div className="max-w-md rounded-xl border border-red-200 bg-white p-6 shadow-sm dark:border-red-900 dark:bg-gray-800">
            <h2 className="mb-2 text-lg font-semibold text-red-600 dark:text-red-400">
              出现了一个错误 / Something went wrong
            </h2>
            <p className="mb-4 text-sm text-gray-700 dark:text-gray-300">
              {this.state.error.message || String(this.state.error)}
            </p>
            <details className="mb-4">
              <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400">
                Stack trace
              </summary>
              <pre className="mt-2 max-h-40 overflow-auto rounded bg-gray-100 p-2 text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-200">
                {this.state.error.stack}
              </pre>
            </details>
            <button
              type="button"
              onClick={this.handleReset}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              重试 / Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
