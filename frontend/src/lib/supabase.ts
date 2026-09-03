import { createClient } from "@supabase/supabase-js";

// Ensure variables are defined, fallback to empty string to avoid Vite crash during build
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "";
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || "";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
