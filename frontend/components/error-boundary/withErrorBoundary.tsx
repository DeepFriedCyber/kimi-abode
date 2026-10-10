/**
 * Error Boundary Higher Order Component for React client-side components.
 * Provides graceful error handling without crashing the entire app.
 */

import React, { Component, ErrorInfo, ReactNode } from "react";
import type { FunctionComponent, FC } from "react";

/** Props for withErrorBoundary HOC. */
export interface ErrorBoundaryProps {
  /** Maximum depth for nested error boundaries (prevent infinite recursion). */
  maxDepth?: number;
}

/** Default error boundary state and actions. */
interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string | null;
  errorComponentStack: string | null;
  renderChildren: boolean;
  depth: number;
}

const DEFAULT_MAX_DEPTH = 5;

/** React Error Boundary component that catches errors in children. */
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private _depthCounter = 0;

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      errorMessage: null,
      errorComponentStack: null,
      renderChildren: true,
      depth: 0,
    };
  }

  static getDerivedStateFromError(
    error: Error,
    info?: ErrorInfo,
  ): Partial<ErrorBoundaryState> {
    console.error("[ErrorBoundary] Caught error:", error);
    if (info?.componentStack) {
      console.error("[ErrorBoundary] Component stack:\n", info.componentStack);
    }
    return {
      hasError: true,
      errorMessage: error.message,
      errorComponentStack: info?.componentStack || null,
      renderChildren: false,
    };
  }

  private _resetDepth(): void {
    this._depthCounter--;
    if (this.state.depth > 0) {
      this.setState((prev) => ({ depth: prev.depth - 1 }));
    }
  }

  componentDidCatch(error: Error, info?: ErrorInfo): void {
    // Ensure we don't exceed max depth
    if (this._depthCounter >= DEFAULT_MAX_DEPTH) {
      console.error(
        "[ErrorBoundary] Max depth reached for error boundary.",
        "Stack trace:",
        info?.componentStack || String(error),
      );
    } else {
      this.setState({ hasError: true });
    }
  }

  private _tryCatch<T>(fn: () => T): T | null {
    try {
      return fn();
    } catch (err) {
      console.error("[ErrorBoundary] Error in wrapped function:", err);
      return null;
    }
  }

  public componentDidReset(): void {
    this.setState({ hasError: false, errorMessage: null });
  }

  public reset(): void {
    this._tryCatch(() => {
      if (this.state.depth > 0) {
        this.setState((prev) => ({ depth: prev.depth - 1 }));
        this.setState({ hasError: false, errorMessage: null });
      } else {
        this.setState({ hasError: false, errorMessage: null });
      }
    });
  }

  private _handleResetClick(): void {
    if (this.state.hasError) {
      this.reset();
    }
  }

  public render(): ReactNode {
    const { children, maxDepth = DEFAULT_MAX_DEPTH } = this.props;

    // If we've hit max depth, stop nesting more boundaries
    if (this._depthCounter >= maxDepth) {
      return children as ReactNode;
    }

    // Increment depth for nested boundaries
    this._depthCounter++;
    const depth = this.state.depth + 1;
    this.setState((prev) => ({ depth }));

    const ErrorBoundaryComponent = this.constructor as typeof ErrorBoundary;

    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-8">
          <div className="max-w-lg text-center space-y-6">
            <h1 className="text-3xl font-bold text-red-600">Something went wrong</h1>
            <p className="text-gray-700">{this.state.errorMessage}</p>
            {this.state.errorComponentStack && (
              <pre className="bg-black text-green-400 p-4 rounded-lg text-xs overflow-auto max-h-64">
                {this.state.errorComponentStack}
              </pre>
            )}
            <div className="space-y-3">
              <button
                onClick={this._handleResetClick}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
              >
                Reload Component
              </button>
              <a
                href="/"
                className="px-4 py-2 text-blue-600 hover:underline"
              >
                Go to Home
              </a>
            </div>
          </div>
        </div>
      );
    }

    return (
      <ErrorBoundaryComponent maxDepth={maxDepth}>
        {children}
      </ErrorBoundaryComponent>
    );
  }
}

/** Error Boundary HOC factory function. */
export function withErrorBoundary<
  P extends Record<string, unknown>,
>(
  WrappedComponent: FunctionComponent<P>,
): FC<P & { onError?: (error: Error) => void }> {
  return function ErrorBoundaryWrapper({ onError, ...rest }: any) {
    // Check if component is currently rendering successfully
    let hasError = false;
    let errorMessage: string | null = null;

    const handleError = (err: unknown): void => {
      console.error("[withErrorBoundary] Wrapped component error:", err);
      if (onError) {
        onError(err instanceof Error ? err : new Error(String(err)));
      } else {
        hasError = true;
        errorMessage = String(err);
      }
    };

    const renderFallback = (): ReactNode => (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-8">
        <div className="max-w-lg text-center space-y-6">
          <h1 className="text-3xl font-bold text-red-600">Something went wrong</h1>
          <p className="text-gray-700">{errorMessage || "An unexpected error occurred"}</p>
          <div className="space-y-3">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            >
              Reload Page
            </button>
            <a href="/" className="px-4 py-2 text-blue-600 hover:underline">
              Go to Home
            </a>
          </div>
        </div>
      </div>
    );

    try {
      return (
        <ErrorBoundary maxDepth={5}>
          <WrappedComponent {...(rest as P)} />
        </ErrorBoundary>
      );
    } catch (renderErr) {
      // Fallback if component itself fails to render
      handleError(renderErr);
      return renderFallback();
    }
  };
}

/** Simple Error Boundary class for server components or SSR. */
export class ServerErrorBoundary extends React.Component<
  { fallback?: ReactNode },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { fallback?: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): { hasError: boolean } {
    console.error("[ServerErrorBoundary] Caught error:", error);
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="text-center p-8 text-red-600">
          An error occurred rendering this component.
        </div>
      );
    }
    return this.props.children;
  }
}