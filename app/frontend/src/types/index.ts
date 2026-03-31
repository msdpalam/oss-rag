export interface User {
  id: string;
  email: string;
  display_name?: string;
  created_at: string;
}

export interface Session {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  last_message_at?: string;
  message_count: number;
  is_archived: boolean;
}

export interface CitedChunk {
  id: string;
  score: number;
  source: string;
  page?: number;
  content: string;
  content_type: 'text' | 'table' | 'image_caption';
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  retrieved_chunks?: CitedChunk[];
  search_query?: string;
  model_used?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  latency_ms?: number;
  feedback?: 'up' | 'down';
  feedback_at?: string;
  // Agent identity (set when streamed via the done event)
  agent_id?: string;
  agent_character?: string;
  agent_title?: string;
}

export interface InvestorProfile {
  age?: number | null;
  risk_tolerance?: number | null;
  horizon_years?: number | null;
  goals: string[];
  portfolio_size_usd?: number | null;
  monthly_contribution_usd?: number | null;
  tax_accounts: string[];
  preferred_agent: string;
  updated_at?: string | null;
}

export interface Document {
  id: string;
  filename: string;
  original_name: string;
  content_type?: string;
  size_bytes?: number;
  status: 'uploaded' | 'processing' | 'indexed' | 'failed';
  error_message?: string;
  page_count?: number;
  chunk_count?: number;
  has_images?: boolean;
  created_at: string;
  updated_at: string;
  indexed_at?: string;
  title?: string;
}

// SSE streaming event types (matches backend agents/orchestrator.py)
export type StreamEvent =
  | { type: 'session';     session_id: string; message_id: string; agent_id: string; agent_character: string; agent_title: string }
  | { type: 'tool_call';   tool: string; input: Record<string, unknown>; step: number }
  | { type: 'tool_result'; tool: string; result: string; step: number }
  | { type: 'delta';       text: string }
  | { type: 'done';        latency_ms: number; steps: number; chunks: CitedChunk[]; agent_id: string; agent_character: string; agent_title: string }
  | { type: 'error';       message: string };

export type ChatMode = 'strict_rag' | 'expert_context';

export type AgentId =
  | 'auto'
  | 'equity_analyst'
  | 'technical_trader'
  | 'macro_strategist'
  | 'retirement_planner'
  | 'crypto_analyst'
  | 'portfolio_strategist';

export interface ChatRequest {
  message: string;
  session_id?: string;
  top_k?: number;
  filter_document_ids?: string[];
  rewrite_query?: boolean;
  mode?: ChatMode;
  agent_id?: AgentId;
}
