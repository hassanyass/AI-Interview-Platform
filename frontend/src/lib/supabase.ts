import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { config, configProblems } from "../config";

// createClient("") throws at module load, which used to be the only signal
// that the env was incomplete (a blank page). When the config is invalid we
// export a client that fails on use instead; main.tsx has already replaced
// the app with the configuration-error screen, so nothing reaches it.
function failingClient(): SupabaseClient {
  const reason = `Supabase client unavailable: ${configProblems.join("; ")}`;
  return new Proxy({} as SupabaseClient, {
    get() {
      throw new Error(reason);
    },
  });
}

export const supabase: SupabaseClient =
  config.supabaseUrl && config.supabasePublishableKey
    ? createClient(config.supabaseUrl, config.supabasePublishableKey)
    : failingClient();
