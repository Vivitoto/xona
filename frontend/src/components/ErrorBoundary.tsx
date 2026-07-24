import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorNotice, describeError } from "./ErrorNotice";

interface ErrorBoundaryProps {
  children: ReactNode;
  resetKey?: string;
  onReturnHome?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    error: null,
    errorInfo: null,
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error("Xona page render failed", error, errorInfo);
  }

  componentDidUpdate(previousProps: ErrorBoundaryProps) {
    if (previousProps.resetKey !== this.props.resetKey && this.state.error) {
      this.reset();
    }
  }

  reset = () => {
    this.setState({ error: null, errorInfo: null });
  };

  returnHome = () => {
    this.reset();
    this.props.onReturnHome?.();
  };

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div className="page-stack page-error-fallback">
        <ErrorNotice
          title="页面出错了"
          message="可以重试，或返回仪表盘。"
          details={
            <code aria-label="错误摘要">
              {describeError(this.state.error, "页面渲染失败")}
            </code>
          }
          actions={[
            { label: "重试当前页面", onClick: this.reset },
            { label: "返回仪表盘", onClick: this.returnHome, variant: "secondary" },
          ]}
        />
        {this.state.errorInfo?.componentStack ? (
          <details className="error-stack">
            <summary>技术详情</summary>
            <pre>{this.state.errorInfo.componentStack}</pre>
          </details>
        ) : null}
      </div>
    );
  }
}
