export const MAX_ANALYZE_RETRIES = 1;

export type AnalyzeSkeleton<TGroup = unknown> = {
  groups: TGroup[];
  years: string[];
};

export type AnalyzePayload = {
  ticker: string;
  rows: readonly unknown[];
  years: readonly string[];
};

export type AnalyzeView<
  TData extends AnalyzePayload = AnalyzePayload,
  TGroup = unknown,
> =
  | { kind: 'idle' }
  | {
      kind: 'waiting';
      ticker: string;
      startedAt: number;
      skeleton: AnalyzeSkeleton<TGroup>;
    }
  | { kind: 'ready'; data: TData }
  | { kind: 'error'; message: string };

export type AnalyzeFlowState<
  TData extends AnalyzePayload = AnalyzePayload,
  TGroup = unknown,
> = {
  requestId: number;
  retries: number;
  view: AnalyzeView<TData, TGroup>;
};

export type AnalyzeFlowEvent<
  TData extends AnalyzePayload = AnalyzePayload,
  TGroup = unknown,
> =
  | {
      type: 'start';
      ticker: string;
      startedAt: number;
      skeleton: AnalyzeSkeleton<TGroup>;
    }
  | { type: 'contract_groups'; startedAt: number; groups: TGroup[] }
  | {
      type: 'reply_ok';
      requestId: number;
      data: TData;
      fallbackMessage?: string;
    }
  | { type: 'reply_transient'; requestId: number; message: string }
  | { type: 'reply_product_error'; requestId: number; message: string }
  | { type: 'timeout'; requestId: number; message: string };

export function createInitialAnalyzeFlowState<
  TData extends AnalyzePayload = AnalyzePayload,
  TGroup = unknown,
>(): AnalyzeFlowState<TData, TGroup> {
  return {
    requestId: 0,
    retries: 0,
    view: { kind: 'idle' },
  };
}

export function reduceAnalyzeFlow<
  TData extends AnalyzePayload = AnalyzePayload,
  TGroup = unknown,
>(
  state: AnalyzeFlowState<TData, TGroup>,
  event: AnalyzeFlowEvent<TData, TGroup>,
): AnalyzeFlowState<TData, TGroup> {
  switch (event.type) {
    case 'start':
      return {
        requestId: state.requestId + 1,
        retries: 0,
        view: {
          kind: 'waiting',
          ticker: event.ticker,
          startedAt: event.startedAt,
          skeleton: event.skeleton,
        },
      };
    case 'contract_groups':
      if (
        state.view.kind !== 'waiting' ||
        state.view.startedAt !== event.startedAt ||
        event.groups.length === 0
      ) {
        return state;
      }
      return {
        ...state,
        view: {
          ...state.view,
          skeleton: {
            ...state.view.skeleton,
            groups: event.groups,
          },
        },
      };
    case 'reply_ok':
      if (event.requestId !== state.requestId || state.view.kind !== 'waiting') {
        return state;
      }
      if (!event.data.rows.length || !event.data.years.length) {
        return {
          ...state,
          view: {
            kind: 'error',
            message: event.fallbackMessage ?? 'Backend returned no metric table',
          },
        };
      }
      return {
        ...state,
        view: {
          kind: 'ready',
          data: event.data,
        },
      };
    case 'reply_transient':
    case 'timeout':
      if (event.requestId !== state.requestId || state.view.kind !== 'waiting') {
        return state;
      }
      if (state.retries < MAX_ANALYZE_RETRIES) {
        return {
          ...state,
          retries: state.retries + 1,
        };
      }
      return {
        ...state,
        view: {
          kind: 'error',
          message: event.message,
        },
      };
    case 'reply_product_error':
      if (event.requestId !== state.requestId || state.view.kind !== 'waiting') {
        return state;
      }
      return {
        ...state,
        view: {
          kind: 'error',
          message: event.message,
        },
      };
  }
}
