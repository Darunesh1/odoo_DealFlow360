/** Mirrors Role in backend/app/models/user.py. A user may hold several. */
export const ROLES = ["admin", "sales_rep", "sales_manager", "finance", "customer"] as const

export type Role = (typeof ROLES)[number]

/** Human labels for each role, used everywhere a role is displayed. */
export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  sales_rep: "Sales Rep",
  sales_manager: "Sales Manager",
  finance: "Finance / Ops",
  customer: "Customer",
}

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  /** False while an invitation has been sent but not yet accepted. */
  is_verified: boolean
  roles: Role[]
  created_at: string
  updated_at: string
}

export const PRODUCT_UNITS = ["each", "hour", "day", "license", "recurring"] as const
export type ProductUnit = (typeof PRODUCT_UNITS)[number]

export const RECURRING_INTERVALS = ["weekly", "monthly", "quarterly", "yearly"] as const
export type RecurringInterval = (typeof RECURRING_INTERVALS)[number]

export const LINE_SOURCES = ["manual", "upsell", "cross_sell"] as const
export type LineSource = (typeof LINE_SOURCES)[number]

export const QUOTATION_STATUSES = [
  "draft",
  "pending_approval",
  "approved",
  "rejected",
  "negotiation",
  "confirmed",
  "cancelled",
] as const
export type QuotationStatus = (typeof QUOTATION_STATUSES)[number]

export const RISK_BANDS = ["none", "low", "medium", "high"] as const
export type RiskBand = (typeof RISK_BANDS)[number]

export const APPROVAL_STATUSES = [
  "pending",
  "approved",
  "auto_approved",
  "returned",
  "rejected",
  "cancelled",
] as const
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number]

export const APPROVAL_STEP_STATUSES = [
  "pending",
  "approved",
  "returned",
  "rejected",
  "skipped",
] as const
export type ApprovalStepStatus = (typeof APPROVAL_STEP_STATUSES)[number]

export const APPROVAL_TRIGGERS = ["rep_submit", "rep_resubmit", "customer_counter"] as const
export type ApprovalTrigger = (typeof APPROVAL_TRIGGERS)[number]

export interface CustomerTier {
  id: string
  code: string
  name: string
  max_discount_percent: number
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface PriceListRef {
  id: string
  name: string
  currency: string
}

export interface Customer {
  id: string
  name: string
  tier_id: string
  default_price_list_id: string | null
  contact_email: string | null
  phone: string | null
  billing_address: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  tier: CustomerTier
  default_price_list: PriceListRef | null
}

export interface ProductCategory {
  id: string
  code: string
  name: string
  max_discount_percent: number | null
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Product {
  id: string
  sku: string
  name: string
  category_id: string
  description: string | null
  list_price: number
  unit_cost: number
  unit: ProductUnit
  tax_percent: number
  is_subscription: boolean
  recurring_interval: RecurringInterval | null
  is_promoted: boolean
  promotion_label: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  category: ProductCategory
}

export interface PriceListItem {
  id: string
  price_list_id: string
  product_id: string
  unit_price: number
  created_at: string
  updated_at: string
  product_name: string
  sku: string
}

export interface PriceList {
  id: string
  name: string
  tier_id: string | null
  currency: string
  adjustment_percent: number
  is_active: boolean
  created_at: string
  updated_at: string
  tier: CustomerTier | null
  items: PriceListItem[]
}

export interface Warehouse {
  id: string
  code: string
  name: string
  address: string | null
  shipping_base_cost: number
  shipping_cost_per_unit: number
  shipping_cost_weight: number
  split_priority: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface StockItem {
  id: string
  warehouse_id: string
  product_id: string
  quantity_on_hand: number
  quantity_reserved: number
  quantity_available: number
  reorder_point: number
  reorder_quantity: number
  lead_time_days: number
  bin_location: string | null
  created_at: string
  updated_at: string
  warehouse_name: string
  warehouse_code: string
  product_name: string
  sku: string
}

export interface QuotationLine {
  id: string
  quotation_id: string
  position: number
  product_id: string | null
  category_id: string | null
  warehouse_id: string | null
  product_name: string
  category_name: string | null
  warehouse_name: string | null
  warehouse_code: string | null
  warehouse_bin_location: string | null
  stock_available_at_entry: number | null
  quantity: number
  unit_price: number
  list_price_at_entry: number
  unit_cost: number
  tax_percent: number
  line_discount_percent: number
  discount_percent: number
  tier_limit_percent: number | null
  category_limit_percent: number | null
  allowed_discount_percent: number
  over_by_points: number
  line_net: number
  line_tax: number
  line_total: number
  is_recurring: boolean
  recurring_interval: RecurringInterval | null
  selected_options: Record<string, unknown>[]
  source: LineSource
  upsell_source_product_id: string | null
  created_at: string
  updated_at: string
}

export interface ApprovalStep {
  id: string
  approval_id: string
  step_order: number
  role: Role
  status: ApprovalStepStatus
  assignee_id: string | null
  assignee_name: string | null
  decided_by_id: string | null
  decided_by_name: string | null
  decided_at: string | null
  note: string | null
}

export interface Approval {
  id: string
  quotation_id: string
  round_number: number
  rule_id: string | null
  rule_name: string
  blended_risk_score: number
  risk_band: RiskBand
  quotation_total: number
  discount_total: number
  status: ApprovalStatus
  trigger: ApprovalTrigger
  submitted_by_id: string | null
  submitted_by_name: string
  submitted_at: string
  decided_at: string | null
  steps: ApprovalStep[]
}

export interface Quotation {
  id: string
  number: string
  customer_id: string
  recipient_email: string | null
  owner_id: string | null
  owner_name: string | null
  sales_team_id: string | null
  status: QuotationStatus
  price_list_id: string | null
  currency: string
  customer_tier_id: string | null
  tier_max_discount_percent: number | null
  order_discount_percent: number
  subtotal: number
  discount_total: number
  tax_total: number
  total: number
  margin_total: number
  blended_risk_score: number
  risk_band: RiskBand
  max_line_over_points: number
  weighted_over_points: number
  requires_approval: boolean
  current_round: number
  requested_delivery_date: string | null
  promised_delivery_date: string | null
  valid_until: string | null
  last_activity_at: string | null
  confirmed_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
  customer: Customer
  price_list: PriceListRef | null
  customer_tier: CustomerTier | null
  lines: QuotationLine[]
  approval: Approval | null
}

export interface QuotationSubmitResponse {
  quotation: Quotation
  approval_required: boolean
  approval: Approval | null
}

export interface CustomerTierCreateInput {
  code: string
  name: string
  max_discount_percent?: number | null
  sort_order?: number
  is_active?: boolean
}

export interface CustomerTierUpdateInput {
  code?: string
  name?: string
  max_discount_percent?: number | null
  sort_order?: number
  is_active?: boolean
}

export interface ProductCategoryCreateInput {
  code: string
  name: string
  max_discount_percent?: number | null
  sort_order?: number
  is_active?: boolean
}

export interface ProductCategoryUpdateInput {
  code?: string
  name?: string
  max_discount_percent?: number | null
  sort_order?: number
  is_active?: boolean
}

export interface ProductCreateInput {
  sku: string
  name: string
  category_id: string
  description?: string | null
  list_price: number
  unit_cost?: number
  unit?: ProductUnit
  tax_percent?: number
  is_subscription?: boolean
  recurring_interval?: RecurringInterval | null
  is_promoted?: boolean
  promotion_label?: string | null
  is_active?: boolean
}

export interface ProductUpdateInput {
  sku?: string
  name?: string
  category_id?: string
  description?: string | null
  list_price?: number
  unit_cost?: number
  unit?: ProductUnit
  tax_percent?: number
  is_subscription?: boolean
  recurring_interval?: RecurringInterval | null
  is_promoted?: boolean
  promotion_label?: string | null
  is_active?: boolean
}

export interface PriceListCreateInput {
  name: string
  tier_id?: string | null
  currency?: string
  adjustment_percent?: number
  is_active?: boolean
}

export interface PriceListUpdateInput {
  name?: string
  tier_id?: string | null
  currency?: string
  adjustment_percent?: number
  is_active?: boolean
}

export interface PriceListItemUpsertInput {
  product_id: string
  unit_price: number
}

export interface WarehouseCreateInput {
  code: string
  name: string
  address?: string | null
  shipping_base_cost?: number
  shipping_cost_per_unit?: number
  shipping_cost_weight?: number
  split_priority?: number
  is_active?: boolean
}

export interface WarehouseUpdateInput {
  code?: string
  name?: string
  address?: string | null
  shipping_base_cost?: number
  shipping_cost_per_unit?: number
  shipping_cost_weight?: number
  split_priority?: number
  is_active?: boolean
}

export interface StockUpsertInput {
  warehouse_id: string
  product_id: string
  quantity_on_hand: number
  quantity_reserved?: number
  reorder_point?: number
  reorder_quantity?: number
  lead_time_days?: number
  bin_location?: string | null
}

export interface CustomerCreateInput {
  name: string
  tier_id: string
  default_price_list_id?: string | null
  contact_email?: string | null
  phone?: string | null
  billing_address?: string | null
  is_active?: boolean
}

export interface CustomerUpdateInput {
  name?: string
  tier_id?: string
  default_price_list_id?: string | null
  contact_email?: string | null
  phone?: string | null
  billing_address?: string | null
  is_active?: boolean
}

export interface QuotationCreateInput {
  customer_id: string
  price_list_id?: string | null
  recipient_email?: string | null
  order_discount_percent?: number
  notes?: string | null
  requested_delivery_date?: string | null
  valid_until?: string | null
}

export interface QuotationUpdateInput {
  price_list_id?: string | null
  recipient_email?: string | null
  order_discount_percent?: number
  notes?: string | null
  requested_delivery_date?: string | null
  promised_delivery_date?: string | null
  valid_until?: string | null
}

export interface QuotationLineCreateInput {
  product_id: string
  quantity: number
  line_discount_percent?: number
  selected_options?: Record<string, unknown>[]
  source?: LineSource
}

export interface QuotationLineUpdateInput {
  quantity?: number
  line_discount_percent?: number
  selected_options?: Record<string, unknown>[]
  source?: LineSource
}

export interface QuotationDiscountUpdateInput {
  order_discount_percent: number
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Message {
  message: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

/** Shape of FastAPI's error responses: a string, or a list of validation errors. */
export interface ApiErrorBody {
  detail?: string | { msg: string; loc?: (string | number)[] }[]
}
