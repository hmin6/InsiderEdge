import { Component, type ReactNode } from 'react';
import { StateMessage } from './ui';
export class PanelBoundary extends Component<{ children: ReactNode; label: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <StateMessage kind="error" title={`${this.props.label} unavailable`} actions={<><button className="ie-button" onClick={() => this.setState({ failed: false })}>Retry panel</button><a className="ie-button" href="/">Return to Radar</a></>}>Other research results remain usable.</StateMessage> : this.props.children;
  }
}
