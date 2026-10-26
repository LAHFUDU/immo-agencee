export interface UserRef {
  id: string;
  full_name: string;
}

export interface Owner {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  company: string | null;
  notes: string | null;
}

export interface Photo {
  id: string;
  filename: string;
  position: number;
  url: string;
}

export interface Property {
  id: string;
  reference: string;
  property_type: string;
  transaction_type: "sale" | "rent";
  title: string;
  description: string | null;
  city: string;
  neighborhood: string | null;
  surface: string | null;
  price: string;
  currency: string;
  bedrooms: number | null;
  bathrooms: number | null;
  floor: number | null;
  features: string[];
  status: string;
  status_changed_at: string;
  is_published: boolean;
  responsible: UserRef | null;
  photos: Photo[];
  created_at: string;
  updated_at: string;
  address: string | null;
  latitude: string | null;
  longitude: string | null;
  internal_notes: string | null;
  owner: Owner | null;
  confidential_visible: boolean;
  active_match_count: number | null;
}

export interface Customer {
  id: string;
  reference: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  preferred_contact: string;
  source: string;
  preferences: string | null;
  internal_notes: string | null;
  assigned_agent: UserRef | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerRequest {
  id: string;
  reference: string;
  customer: Customer;
  property_type: string;
  transaction_type: "sale" | "rent";
  budget_min: string | null;
  budget_max: string | null;
  currency: string;
  city: string;
  neighborhood: string | null;
  surface_min: string | null;
  surface_max: string | null;
  bedrooms_min: number | null;
  bathrooms_min: number | null;
  required_features: string[];
  preferred_features: string[];
  comments: string | null;
  internal_notes: string | null;
  priority: string;
  status: string;
  source: string;
  assigned_agent: UserRef | null;
  assigned_at: string | null;
  next_follow_up_at: string | null;
  first_contacted_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
  matches: { active_count: number; best_score: number | null; best_category: string | null };
}

export interface Match {
  id: string | null;
  request_id: string;
  property_id: string;
  property_reference: string;
  property_title: string;
  property_city: string;
  property_neighborhood: string | null;
  property_price: string;
  property_currency: string;
  property_surface: string | null;
  property_bedrooms: number | null;
  property_status: string;
  property_photo: string | null;
  request_reference: string | null;
  customer_name: string | null;
  agent: UserRef | null;
  score: number;
  category: string;
  explanation: { met: string[]; unmet: string[]; failed: string[] };
  is_active: boolean;
  status: string | null;
  customer_feedback: string | null;
  rejection_reason: string | null;
  computed_at: string | null;
  notified_at: string | null;
}

export interface Activity {
  id: string;
  type: string;
  summary: string;
  occurred_at: string;
  customer_id: string | null;
  request_id: string | null;
  property_id: string | null;
  deal_id: string | null;
  created_by: UserRef | null;
  created_at: string;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  due_at: string;
  status: string;
  assigned_to: UserRef;
  customer_id: string | null;
  request_id: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Visit {
  id: string;
  request_id: string | null;
  request_reference: string | null;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  property_id: string;
  property_reference: string;
  property_title: string;
  property_city: string;
  property_address: string | null;
  agent: UserRef | null;
  scheduled_at: string;
  duration_minutes: number;
  status: string;
  notes: string | null;
  customer_feedback: string | null;
  created_at: string;
}

export interface Offer {
  id: string;
  amount: string;
  party: string;
  status: string;
  notes: string | null;
  offered_at: string;
}

export interface Deal {
  id: string;
  reference: string;
  customer_id: string;
  customer_name: string;
  request_id: string | null;
  property_id: string;
  property_reference: string;
  property_title: string;
  property_status: string;
  agent: UserRef | null;
  transaction_type: "sale" | "rent";
  status: string;
  asking_price: string | null;
  agreed_price: string | null;
  currency: string;
  commission_rate: string | null;
  commission_amount: string | null;
  commission_overridden: boolean;
  expected_closing_date: string | null;
  actual_closing_date: string | null;
  lost_reason: string | null;
  notes: string | null;
  holds_reservation: boolean;
  reservation_override: boolean;
  offers: Offer[];
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  is_read: boolean;
  email_status: string | null;
  created_at: string;
}

export interface CatalogItem {
  code: string;
  label: string;
  is_active: boolean;
  sort_order: number;
  has_rooms?: boolean;
}

export interface Catalog {
  property_types: CatalogItem[];
  features: CatalogItem[];
  cities: string[];
  currency: string;
}

export interface UserAccount {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  job_title: string | null;
  role_id: string;
  role_name: string;
  role_code: string;
  is_active: boolean;
  is_agent: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Role {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_system: boolean;
  is_superadmin: boolean;
  permissions: string[];
}

export interface DuplicateCandidate {
  id: string;
  reference: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  reason: string;
}
