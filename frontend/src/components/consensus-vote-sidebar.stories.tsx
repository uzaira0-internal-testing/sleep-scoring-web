import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useMemo } from "react";
import { fn } from "storybook/test";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { useSleepScoringStore } from "@/store";
import type { ConsensusBallotResponse, ConsensusBallotCandidate } from "@/api/types";
import { ConsensusVoteSidebar } from "./consensus-vote-sidebar";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Sets Zustand store state for the story and resets on unmount. */
function StoreConfigurator({
  state,
  children,
}: {
  state: Record<string, unknown>;
  children: React.ReactNode;
}) {
  useEffect(() => {
    useSleepScoringStore.setState(state);
    return () => {
      useSleepScoringStore.setState({
        currentFileId: null,
        currentDateIndex: 0,
        availableDates: [],
        username: "",
        sitePassword: null,
      });
    };
  }, [state]);
  return <>{children}</>;
}

/** Create a QueryClient pre-seeded with ballot data. */
function createSeededQueryClient(
  fileId: number,
  date: string,
  username: string,
  ballot: ConsensusBallotResponse | null,
): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
    },
  });
  if (ballot) {
    client.setQueryData(["consensus-ballot", fileId, date, username], ballot);
  }
  return client;
}

const BASE_STORE_STATE = {
  currentFileId: 1,
  currentDateIndex: 0,
  availableDates: ["2025-01-15"],
  username: "scorer_a",
  sitePassword: null,
  isAuthenticated: true,
};

// ---------------------------------------------------------------------------
// Mock candidates and ballots
// ---------------------------------------------------------------------------

const ONSET_TS = new Date("2025-01-15T23:00:00Z").getTime() / 1000;
const OFFSET_TS = new Date("2025-01-16T07:00:00Z").getTime() / 1000;
const ALT_ONSET_TS = new Date("2025-01-15T22:45:00Z").getTime() / 1000;
const ALT_OFFSET_TS = new Date("2025-01-16T06:30:00Z").getTime() / 1000;

const CANDIDATE_A: ConsensusBallotCandidate = {
  candidate_id: 1,
  label: "Scorer A",
  source_type: "user",
  sleep_markers_json: [
    { onset_timestamp: ONSET_TS, offset_timestamp: OFFSET_TS, marker_type: "MAIN_SLEEP", marker_index: 0 },
  ],
  nonwear_markers_json: null,
  is_no_sleep: false,
  vote_count: 2,
  selected_by_me: false,
  created_at: "2025-01-15T18:00:00Z",
};

const CANDIDATE_B: ConsensusBallotCandidate = {
  candidate_id: 2,
  label: "Scorer B",
  source_type: "user",
  sleep_markers_json: [
    { onset_timestamp: ALT_ONSET_TS, offset_timestamp: ALT_OFFSET_TS, marker_type: "MAIN_SLEEP", marker_index: 0 },
  ],
  nonwear_markers_json: null,
  is_no_sleep: false,
  vote_count: 1,
  selected_by_me: false,
  created_at: "2025-01-15T18:30:00Z",
};

const CANDIDATE_AUTO: ConsensusBallotCandidate = {
  candidate_id: 3,
  label: "Auto-scored",
  source_type: "auto",
  sleep_markers_json: [
    { onset_timestamp: ONSET_TS, offset_timestamp: ALT_OFFSET_TS, marker_type: "MAIN_SLEEP", marker_index: 0 },
  ],
  nonwear_markers_json: null,
  is_no_sleep: false,
  vote_count: 0,
  selected_by_me: false,
  created_at: "2025-01-15T17:00:00Z",
};

const CANDIDATE_NO_SLEEP: ConsensusBallotCandidate = {
  candidate_id: 4,
  label: "Scorer C",
  source_type: "user",
  sleep_markers_json: [],
  nonwear_markers_json: null,
  is_no_sleep: true,
  vote_count: 0,
  selected_by_me: false,
  created_at: "2025-01-15T19:00:00Z",
};

function buildBallot(
  candidates: ConsensusBallotCandidate[],
  overrides?: Partial<ConsensusBallotResponse>,
): ConsensusBallotResponse {
  const totalVotes = candidates.reduce((sum, c) => sum + c.vote_count, 0);
  const leading = candidates.reduce<ConsensusBallotCandidate | null>(
    (best, c) => (!best || c.vote_count > best.vote_count ? c : best),
    null,
  );
  return {
    file_id: 1,
    analysis_date: "2025-01-15",
    candidates,
    total_votes: totalVotes,
    leading_candidate_id: leading && leading.vote_count > 0 ? leading.candidate_id : null,
    my_vote_candidate_id: candidates.find((c) => c.selected_by_me)?.candidate_id ?? null,
    updated_at: "2025-01-15T19:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Provider wrapper
// ---------------------------------------------------------------------------

function VoteProviders({
  ballot,
  storeState,
  children,
}: {
  ballot: ConsensusBallotResponse | null;
  storeState: Record<string, unknown>;
  children: React.ReactNode;
}) {
  const qc = useMemo(
    () => createSeededQueryClient(1, "2025-01-15", "scorer_a", ballot),
    [ballot],
  );

  return (
    <ThemeProvider defaultTheme="light" storageKey="storybook-consensus">
      <QueryClientProvider client={qc}>
        <StoreConfigurator state={storeState}>
          {children}
        </StoreConfigurator>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Components/ConsensusVoteSidebar",
  component: ConsensusVoteSidebar,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Sidebar panel for consensus voting. Displays candidate marker sets from different scorers, " +
          "allows voting/unvoting, copying candidate markers, and shows a live WebSocket connection indicator. " +
          "Each candidate card shows marker summary, vote count, and action buttons.",
      },
    },
  },
  args: {
    highlightedCandidateId: null,
    onHighlightCandidate: fn(),
    onCopyCandidate: fn(),
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ConsensusVoteSidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Multiple candidates with votes -- Scorer A leads with 2 votes. */
export const WithCandidates: Story = {
  decorators: [
    (Story) => (
      <VoteProviders
        ballot={buildBallot([CANDIDATE_A, CANDIDATE_B, CANDIDATE_AUTO])}
        storeState={BASE_STORE_STATE}
      >
        <div style={{ width: 320, height: 600 }}>
          <Story />
        </div>
      </VoteProviders>
    ),
  ],
};

/** No candidates yet -- shows prompt about saving markers first. */
export const NoCandidates: Story = {
  decorators: [
    (Story) => (
      <VoteProviders
        ballot={buildBallot([])}
        storeState={BASE_STORE_STATE}
      >
        <div style={{ width: 320, height: 400 }}>
          <Story />
        </div>
      </VoteProviders>
    ),
  ],
};

/** User has already voted for Candidate A (checkmark and "Unvote" button shown). */
export const AlreadyVoted: Story = {
  decorators: [
    (Story) => {
      const votedA = { ...CANDIDATE_A, selected_by_me: true };
      return (
        <VoteProviders
          ballot={buildBallot([votedA, CANDIDATE_B])}
          storeState={BASE_STORE_STATE}
        >
          <div style={{ width: 320, height: 500 }}>
            <Story />
          </div>
        </VoteProviders>
      );
    },
  ],
};

/** A candidate is highlighted (clicked for comparison overlay on the activity plot). */
export const HighlightedCandidate: Story = {
  args: {
    highlightedCandidateId: 2,
  },
  decorators: [
    (Story) => (
      <VoteProviders
        ballot={buildBallot([CANDIDATE_A, CANDIDATE_B])}
        storeState={BASE_STORE_STATE}
      >
        <div style={{ width: 320, height: 500 }}>
          <Story />
        </div>
      </VoteProviders>
    ),
  ],
};

/** Includes a no-sleep candidate alongside regular candidates. */
export const WithNoSleepCandidate: Story = {
  decorators: [
    (Story) => (
      <VoteProviders
        ballot={buildBallot([CANDIDATE_A, CANDIDATE_NO_SLEEP])}
        storeState={BASE_STORE_STATE}
      >
        <div style={{ width: 320, height: 500 }}>
          <Story />
        </div>
      </VoteProviders>
    ),
  ],
};

/** Auto-scored candidate (shown with bot icon). */
export const WithAutoScoredCandidate: Story = {
  decorators: [
    (Story) => (
      <VoteProviders
        ballot={buildBallot([CANDIDATE_AUTO, CANDIDATE_B])}
        storeState={BASE_STORE_STATE}
      >
        <div style={{ width: 320, height: 500 }}>
          <Story />
        </div>
      </VoteProviders>
    ),
  ],
};

/** All candidate types together: user, auto, no-sleep, with one voted. */
export const AllCandidateTypes: Story = {
  decorators: [
    (Story) => {
      const votedA = { ...CANDIDATE_A, selected_by_me: true };
      return (
        <VoteProviders
          ballot={buildBallot([votedA, CANDIDATE_B, CANDIDATE_AUTO, CANDIDATE_NO_SLEEP])}
          storeState={BASE_STORE_STATE}
        >
          <div style={{ width: 320, height: 700 }}>
            <Story />
          </div>
        </VoteProviders>
      );
    },
  ],
};
