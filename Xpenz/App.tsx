import { StatusBar } from 'expo-status-bar';
import * as ImagePicker from 'expo-image-picker';
import * as Print from 'expo-print';
import * as SecureStore from 'expo-secure-store';
import * as Sharing from 'expo-sharing';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  NavigationContainer,
  type NavigationContainerRef,
} from '@react-navigation/native';
import {
  CalendarCheck2,
  ChevronRight,
  CircleEllipsis,
  FileText,
  Plus,
  ReceiptText,
  RefreshCcw,
  ShoppingBag,
  Users,
} from 'lucide-react-native';
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  InputAccessoryView,
  Keyboard,
  KeyboardAvoidingView,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  TouchableWithoutFeedback,
  View,
} from 'react-native';
import { GestureHandlerRootView, Swipeable } from 'react-native-gesture-handler';
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

type EstimateRow = {
  id: number;
  estimate_number: number | null;
  job_name: string;
  customer_name: string;
  event_type: string;
  event_date: string;
  event_location: string;
  guest_count: number;
  guest_count_kids: number;
  caterer_id: number;
  caterer_name: string;
  currency: string;
  grand_total: string;
  expense_count: number;
  can_view_billing: boolean;
  can_add_expenses: boolean;
  can_manage_staff: boolean;
  print_urls?: {
    estimate?: string;
    estimate_print?: string;
    estimate_flat?: string;
    estimate_flat_print?: string;
    planner?: string;
    planner_print?: string;
    workflow?: string;
    workflow_print?: string;
  };
};

type MainTab = 'estimates' | 'shopping' | 'planner' | 'expenses' | 'staff';

type RootTabParamList = {
  Estimates: undefined;
  Shopping: undefined;
  Planner: undefined;
  Expenses: undefined;
  Staff: undefined;
};

type EstimatePrintVariant = 'estimate' | 'flat' | 'planner' | 'workflow';

type EstimateBuilderStep =
  | 'customer'
  | 'menu'
  | 'decor'
  | 'addons'
  | 'summary'
  | 'additional';

type EstimateBuilderMenuItem = {
  id: number;
  name: string;
  description: string;
  default_servings_per_person: string;
  cost_per_serving: string;
  markup: string;
  price_per_serving: string;
};

type EstimateBuilderMenuCategory = {
  id: number | null;
  name: string;
  items: EstimateBuilderMenuItem[];
};

type EstimateBuilderExtraItem = {
  id: number;
  name: string;
  category: string;
  category_label: string;
  charge_type: string;
  charge_type_label: string;
  price: string;
  cost: string;
  notes: string;
};

type EstimateBuilderExtraCategory = {
  code: string;
  label: string;
  items: EstimateBuilderExtraItem[];
};

type EstimateBuilderMenuChoice = {
  menu_item_id: number;
  meal_name: string;
  servings_per_person: string;
  notes: string;
  included: boolean;
};

type EstimateBuilderExtraLine = {
  extra_item_id: number;
  quantity: string;
  override_price: string;
  notes: string;
  included: boolean;
};

type EstimateBuilderSummary = {
  waiter_count: number;
  food_total: string;
  food_price_per_person: string;
  extras_total: string;
  staff_total: string;
  dishes_total: string;
  grand_total: string;
  deposit_amount: string;
  balance_due: string;
};

type EstimateBuilderMealSection = {
  name: string;
  price_per_guest: string;
  price_per_child: string;
  total: string;
  kids_total: string;
  guest_count: string;
  guest_count_kids: string;
};

type EstimateBuilderMealGuestOverride = {
  adults?: number;
  kids?: number;
};

type EstimateBuilderMealOverrideDraft = {
  override_price: string;
  adults: string;
  kids: string;
};

type EstimateBuilderEstimate = EstimateRow & {
  can_edit: boolean;
  customer_phone: string;
  customer_email: string;
  is_ala_carte: boolean;
  include_premium_plastic: boolean;
  include_premium_tablecloths: boolean;
  plasticware_color: string;
  wants_real_dishes: boolean;
  real_dishes_price_per_person: string;
  real_dishes_flat_fee: string;
  staff_hours: string;
  extra_waiters: number;
  staff_count_override: number | null;
  staff_hourly_rate: string;
  staff_tip_per_waiter: string;
  client_tipped_at_event: boolean;
  notes_internal: string;
  notes_for_customer: string;
  payment_terms: string;
  payment_method: string;
  payment_instructions: string;
  contract_terms: string;
  terms_acknowledged: boolean;
  signature_name: string;
  signature_title: string;
  signature_date: string;
  deposit_percentage: string;
  deposit_received: string;
  kids_discount_percentage: string;
  exchange_rate: string;
  meal_plan: string[];
  manual_meal_totals: Record<string, string>;
  meal_guest_overrides: Record<string, EstimateBuilderMealGuestOverride>;
  meal_sections: EstimateBuilderMealSection[];
  tablecloth_details: Record<string, unknown>;
  summary: EstimateBuilderSummary;
};

type EstimateBuilderCatalog = {
  currencies: Array<{ code: string; label: string }>;
  payment_methods: Array<{ code: string; label: string }>;
  meal_plan: string[];
  menu_categories: EstimateBuilderMenuCategory[];
  extra_categories: EstimateBuilderExtraCategory[];
  tablecloth_options: string[];
  plasticware_options: string[];
};

type SavedEntry = {
  id: number;
  expense_text: string;
  expense_amount: string;
  is_manual_only: boolean;
  note_text: string;
  voice_note_duration_seconds: number | null;
  created_at: string;
  created_by: string;
  receipt_image_url: string;
  voice_note_url: string;
  has_receipt_image: boolean;
  has_voice_note: boolean;
};

type ExpenseDraft = {
  localId: string;
  manualOnly: boolean;
  receiptUri?: string;
  receiptFileName?: string;
  receiptMimeType?: string;
  voiceUri?: string;
  voiceDurationSeconds?: number;
  expenseText: string;
  expenseAmount: string;
  noteText: string;
};

type StaffRoleOption = {
  code: string;
  label: string;
  hourly_rate: string;
  punch_url: string;
  qr_image_url: string;
};

type StaffEntry = {
  id: number;
  role: string;
  role_label: string;
  worker_first_name: string;
  hourly_rate: string;
  punched_in_at: string;
  punched_out_at: string;
  total_hours: string;
  total_cost: string;
  applied_to_expenses: boolean;
  expense_entry_id: number | null;
};

type ShoppingListRow = {
  id: number;
  title: string;
  caterer_id: number;
  caterer_name: string;
  estimate_id: number | null;
  estimate_label: string;
  item_count: number;
  is_deleted?: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
};

type ShoppingItem = {
  id: number;
  item_name: string;
  item_type: string;
  item_unit: string;
  quantity: string;
  category: string;
  category_label: string;
  collaboration_note: string;
  created_at: string;
};

type ShoppingCatalogItem = {
  item_name: string;
  category: string;
  category_label: string;
  type_options: string[];
  unit_options: string[];
  last_used_unit: string;
  usage_count: number;
};

type ShoppingCatalogCategory = {
  category: string;
  category_label: string;
  items: ShoppingCatalogItem[];
};

type ShoppingCatalogListItem = ShoppingCatalogItem & {
  category: string;
  category_label: string;
};

type PlannerSectionCode =
  | 'DECOR'
  | 'RENTALS'
  | 'ORDERS'
  | 'SPECIAL_REQUESTS'
  | 'PRINTING'
  | 'STAFFING';

type PlannerEntryRow = {
  id: number;
  estimate_id: number;
  section: PlannerSectionCode;
  section_label: string;
  group_code: string;
  group_label: string;
  item_code: string;
  item_label: string;
  data: Record<string, string>;
  data_rows: Array<{ field_code: string; field_label: string; value: string }>;
  notes: string;
  is_checked: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type PlannerMemoryBucket = {
  section: PlannerSectionCode;
  group_code: string;
  item_code: string;
  field_code: string;
  values: string[];
};

type PlannerCatalogItem = {
  section: PlannerSectionCode;
  group_code: string;
  item_code: string;
  item_label: string;
  usage_count: number;
};

type PlannerIconOverride = {
  section: PlannerSectionCode;
  group_code: string;
  item_code: string;
  icon_key: string;
  is_manual_override?: boolean;
};

type PlannerFieldCardRow = {
  section: PlannerSectionCode;
  group_code: string;
  item_code: string;
  field_code: string;
  field_label: string;
  value_options: string[];
  sort_order: number;
};

type PlannerFieldCardPayloadRow = {
  field_code: string;
  field_label: string;
  value_options: string[];
  sort_order: number;
};

type PlannerFieldConfig = {
  code: string;
  label: string;
  placeholder?: string;
  keyboardType?: 'default' | 'decimal-pad';
  multiline?: boolean;
  valueOptions?: string[];
};

type PlannerItemOption = {
  code: string;
  label: string;
  fields?: PlannerFieldConfig[];
};

type PlannerGroupConfig = {
  code: string;
  label: string;
  fields: PlannerFieldConfig[];
  itemOptions?: PlannerItemOption[];
  showGroupCard?: boolean;
};

type PlannerSectionConfig = {
  code: PlannerSectionCode;
  label: string;
  icon: string;
  groups: PlannerGroupConfig[];
};

type PlannerEditorFieldCard = {
  id: string;
  fieldCode: string;
  fieldLabel: string;
  valueOptionsText: string;
  sortOrder: number;
};

type PlannerChecklistCard = {
  key: string;
  groupCode: string;
  itemCode: string;
  label: string;
  secondaryLabel?: string;
  icon: string;
  isAdded: boolean;
  isChecked: boolean;
  summaryLines: string[];
  entries: PlannerEntryRow[];
};

type ApiRequestError = Error & {
  status?: number;
};

const TOKEN_KEY = 'xpenz_token';
const BASE_URL_KEY = 'xpenz_base_url';
const SHOPPING_LAST_QTY_KEY = 'xpenz_shopping_last_qty';
const DEFAULT_BASE_URL = 'https://www.caterbasepro.com';
const SHEKEL_SYMBOL = '₪';
const DEFAULT_SHOPPING_UNIT_OPTIONS = ['Kg', 'Pieces', 'Cans'];
const NUMERIC_INPUT_ACCESSORY_ID = 'xpenz-numeric-accessory';
const TAB_BAR_HEIGHT = 49;
const PDF_A4_WIDTH_POINTS = 595.28;
const PDF_A4_HEIGHT_POINTS = 841.89;
const TAB_NAME_BY_MAIN: Record<MainTab, keyof RootTabParamList> = {
  estimates: 'Estimates',
  shopping: 'Shopping',
  planner: 'Planner',
  expenses: 'Expenses',
  staff: 'Staff',
};
const MAIN_TAB_BY_NAME: Record<keyof RootTabParamList, MainTab> = {
  Estimates: 'estimates',
  Shopping: 'shopping',
  Planner: 'planner',
  Expenses: 'expenses',
  Staff: 'staff',
};
const PLANNER_SECTION_CHOICES: PlannerSectionConfig[] = [
  {
    code: 'DECOR',
    label: 'Decor',
    icon: 'decor',
    groups: [
      {
        code: 'table_cloths',
        label: 'Table Cloths',
        fields: [
          { code: 'color', label: 'Color', placeholder: 'Color' },
          { code: 'fabric', label: 'Fabric', placeholder: 'Fabric' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
      {
        code: 'chad_paami',
        label: 'Chad Paami',
        fields: [
          { code: 'color', label: 'Color', placeholder: 'Color' },
          { code: 'style', label: 'Style', placeholder: 'Style' },
        ],
      },
      {
        code: 'centerpieces',
        label: 'Centerpieces',
        itemOptions: [
          { code: 'floral', label: 'Floral' },
          { code: 'balloon', label: 'Balloon' },
          { code: 'lanterns', label: 'Lanterns' },
        ],
        fields: [
          { code: 'colors', label: 'Colors', placeholder: 'Colors' },
          { code: 'style', label: 'Style', placeholder: 'Style' },
          { code: 'price_per_table', label: 'Price per table', keyboardType: 'decimal-pad', placeholder: '0.00' },
        ],
      },
      {
        code: 'features',
        label: 'Features',
        itemOptions: [
          { code: 'balloon_feature', label: 'Balloon Feature' },
          { code: 'floral_feature', label: 'Floral Feature' },
          { code: 'other', label: 'Other' },
        ],
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'price', label: 'Price', keyboardType: 'decimal-pad', placeholder: '0.00' },
        ],
      },
    ],
  },
  {
    code: 'RENTALS',
    label: 'Rentals',
    icon: 'rentals',
    groups: [
      {
        code: 'furniture',
        label: 'Furniture',
        itemOptions: [
          {
            code: 'tables',
            label: 'Tables',
            fields: [
              { code: 'shape', label: 'Shape', placeholder: 'Shape' },
              { code: 'seat_qty', label: 'Seat Qty', keyboardType: 'decimal-pad', placeholder: 'Seat Qty' },
              { code: 'table_qty', label: 'Table Qty', keyboardType: 'decimal-pad', placeholder: 'Table Qty' },
            ],
          },
          {
            code: 'chairs',
            label: 'Chairs',
            fields: [
              { code: 'type', label: 'Type', placeholder: 'Type' },
              { code: 'color', label: 'Color', placeholder: 'Color' },
              { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
            ],
          },
          {
            code: 'bars',
            label: 'Bars',
            fields: [
              { code: 'type', label: 'Type', placeholder: 'Type' },
              { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
            ],
          },
          {
            code: 'couches',
            label: 'Couches',
            fields: [
              { code: 'size', label: 'Size', placeholder: 'Size' },
              { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
            ],
          },
        ],
        fields: [],
      },
      {
        code: 'addon_features',
        label: 'Addon Features',
        itemOptions: [
          { code: 'chocolate_fountain_rental', label: 'Chocolate Fountain Rental' },
          { code: 'projector_screen_speaker_rental', label: 'Projector + Screen + Speaker Rental' },
        ],
        fields: [
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
          { code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true },
        ],
      },
    ],
  },
  {
    code: 'ORDERS',
    label: 'Orders',
    icon: 'orders',
    groups: [
      {
        code: 'bread_order',
        label: 'Bread Order',
        fields: [
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
          { code: 'supplier', label: 'Supplier', placeholder: 'Supplier' },
          { code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true },
        ],
      },
      {
        code: 'dishes_order',
        label: 'Dishes Order',
        fields: [
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
          { code: 'supplier', label: 'Supplier', placeholder: 'Supplier' },
          { code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true },
        ],
      },
      {
        code: 'tablecloth_order',
        label: 'Tablecloth Order',
        fields: [
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
          { code: 'supplier', label: 'Supplier', placeholder: 'Supplier' },
          { code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true },
        ],
      },
    ],
  },
  {
    code: 'SPECIAL_REQUESTS',
    label: 'Special Requests',
    icon: 'special_requests',
    groups: [
      {
        code: 'special_requests',
        label: 'Special Requests',
        fields: [{ code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true }],
      },
    ],
  },
  {
    code: 'PRINTING',
    label: 'Printing',
    icon: 'printing',
    groups: [
      {
        code: 'sign',
        label: 'Sign',
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'size', label: 'Size', placeholder: 'Size' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
      {
        code: 'invitations',
        label: 'Invitations',
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
      {
        code: 'placecards',
        label: 'Placecards',
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
      {
        code: 'menus',
        label: 'Menus',
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
      {
        code: 'signing_boards',
        label: 'Signing Boards',
        fields: [
          { code: 'type', label: 'Type', placeholder: 'Type' },
          { code: 'size', label: 'Size', placeholder: 'Size' },
          { code: 'qty', label: 'Qty', keyboardType: 'decimal-pad', placeholder: 'Qty' },
        ],
      },
    ],
  },
  {
    code: 'STAFFING',
    label: 'Staffing',
    icon: 'staffing',
    groups: [
      {
        code: 'staffing',
        label: 'Staffing',
        fields: [
          { code: 'qty_staff_needed', label: 'Qty Of Staff Needed', keyboardType: 'decimal-pad', placeholder: 'Qty' },
          { code: 'who_hired', label: 'Who has been hired', placeholder: 'Names of hired staff' },
          { code: 'notes', label: 'Notes', placeholder: 'Notes', multiline: true },
        ],
      },
    ],
  },
];

const PLANNER_SECTION_ICON_MAP: Record<string, string> = {
  decor: 'palette',
  rentals: 'armchair',
  orders: 'clipboard',
  special_requests: 'file',
  printing: 'printer',
  staffing: 'users',
};

const PLANNER_ITEM_ICON_MAP: Record<string, string> = {
  'DECOR|table_cloths|': 'table',
  'DECOR|chad_paami|': 'package',
  'DECOR|centerpieces|floral': 'sparkles',
  'DECOR|centerpieces|balloon': 'sparkles',
  'DECOR|centerpieces|lanterns': 'sparkles',
  'DECOR|features|balloon_feature': 'sparkles',
  'DECOR|features|floral_feature': 'sparkles',
  'DECOR|features|other': 'sparkles',
  'RENTALS|furniture|tables': 'table',
  'RENTALS|furniture|chairs': 'armchair',
  'RENTALS|furniture|bars': 'package',
  'RENTALS|furniture|couches': 'armchair',
  'RENTALS|addon_features|chocolate_fountain_rental': 'package',
  'RENTALS|addon_features|projector_screen_speaker_rental': 'package',
  'ORDERS|bread_order|': 'clipboard',
  'ORDERS|dishes_order|': 'clipboard',
  'ORDERS|tablecloth_order|': 'clipboard',
  'PRINTING|sign|': 'printer',
  'PRINTING|invitations|': 'printer',
  'PRINTING|placecards|': 'printer',
  'PRINTING|menus|': 'printer',
  'PRINTING|signing_boards|': 'printer',
  'STAFFING|staffing|': 'users',
  'SPECIAL_REQUESTS|special_requests|': 'file',
};

const PLANNER_EMOJI_ICON_MAP: Record<string, string> = {
  palette: '🎀',
  armchair: '🪑',
  clipboard: '📦',
  printer: '🖨️',
  users: '👥',
  file: '📝',
  sparkles: '✨',
  table: '🧺',
  package: '📦',
  circle: '◯',
};

const DEFAULT_PLANNER_COLOR_VALUES = [
  'White',
  'Black',
  'Cream',
  'Beige',
  'Gold',
  'Silver',
  'Blue',
  'Navy',
  'Pink',
  'Green',
];
const DEFAULT_PLANNER_PRICE_VALUES = ['250', '500', '800', '1200', '1500', '2000'];
const DEFAULT_PLANNER_QTY_VALUES = ['1', '2', '3', '5', '8', '10', '12', '15', '20'];
const PLANNER_COLOR_HEX_MAP: Record<string, string> = {
  white: '#ffffff',
  black: '#111827',
  cream: '#fff7d6',
  beige: '#e8d8b5',
  gold: '#d4a017',
  silver: '#c0c0c0',
  blue: '#2563eb',
  navy: '#1e3a8a',
  pink: '#ec4899',
  green: '#16a34a',
  red: '#dc2626',
  yellow: '#facc15',
  orange: '#f97316',
  purple: '#7c3aed',
  clear: '#e2e8f0',
  transparent: '#e2e8f0',
};

function renderPlannerIcon(iconKey: string, size = 20, _color = '#0f172a') {
  const glyph = PLANNER_EMOJI_ICON_MAP[iconKey] || iconKey || PLANNER_EMOJI_ICON_MAP.circle;
  return <Text style={{ fontSize: size, lineHeight: size + 2 }}>{glyph}</Text>;
}

function plannerSplitMultiValue(value: string) {
  return (value || '')
    .split(/[,;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function plannerColorHexForValue(value: string) {
  const raw = (value || '').trim().toLowerCase();
  if (!raw) return '';
  const compact = raw.replace(/\s+/g, '_');
  if (PLANNER_COLOR_HEX_MAP[compact]) {
    return PLANNER_COLOR_HEX_MAP[compact];
  }
  if (/^#?[0-9a-f]{6}$/i.test(raw)) {
    return raw.startsWith('#') ? raw : `#${raw}`;
  }
  if (/^#?[0-9a-f]{3}$/i.test(raw)) {
    const short = raw.startsWith('#') ? raw.slice(1) : raw;
    return `#${short[0]}${short[0]}${short[1]}${short[1]}${short[2]}${short[2]}`;
  }
  return '';
}

function plannerTextColorForBackground(hex: string) {
  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) {
    return '#0f172a';
  }
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  if ([r, g, b].some((value) => Number.isNaN(value))) {
    return '#0f172a';
  }
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  return brightness < 150 ? '#ffffff' : '#0f172a';
}

function humanizePlannerCode(value: string) {
  const raw = (value || '').trim().replace(/[_-]+/g, ' ');
  if (!raw) return '';
  return raw
    .split(/\s+/)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(' ');
}

function normalizePlannerCode(value: string) {
  return (value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

const PLANNER_FIELD_TEMPLATE_MAP = (() => {
  const map = new Map<string, PlannerFieldConfig>();
  for (const section of PLANNER_SECTION_CHOICES) {
    for (const group of section.groups) {
      for (const field of group.fields || []) {
        if (!map.has(field.code)) {
          map.set(field.code, field);
        }
      }
      for (const option of group.itemOptions || []) {
        for (const field of option.fields || []) {
          if (!map.has(field.code)) {
            map.set(field.code, field);
          }
        }
      }
    }
  }
  return map;
})();

function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/+$/, '');
}

function apiUrl(baseUrl: string, path: string) {
  const cleanBase = normalizeBaseUrl(baseUrl);
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${cleanBase}${cleanPath}`;
}

function localId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDate(iso: string) {
  if (!iso) return 'No date';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString();
}

function formatDateTime(iso: string) {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

function formatShekel(amount: string) {
  return `${SHEKEL_SYMBOL}${amount}`;
}

function mergeOptionValues(...groups: Array<Array<string> | undefined>) {
  const seen = new Set<string>();
  const merged: string[] = [];
  for (const group of groups) {
    for (const raw of group || []) {
      const value = (raw || '').trim();
      if (!value) continue;
      const key = value.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(value);
    }
  }
  return merged;
}

function parseMealPlanInput(rawValue: string) {
  const names = rawValue
    .replace(/,/g, '\n')
    .split('\n')
    .map((row) => row.trim())
    .filter(Boolean);
  return mergeOptionValues(names.length ? names : ['Signature Menu']);
}

function normalizeEstimateMealKey(value: string) {
  return (value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function parseNonNegativeDecimalInput(rawValue: string) {
  const value = (rawValue || '').trim();
  if (!value) return null;
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return Number.NaN;
  }
  return Number(parsed.toFixed(2));
}

function parseNonNegativeIntegerInput(rawValue: string) {
  const value = (rawValue || '').trim();
  if (!value) return null;
  if (!/^\d+$/.test(value)) {
    return Number.NaN;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return Number.NaN;
  }
  return parsed;
}

function buildPlannerFieldCardsPayload(
  rows: PlannerEditorFieldCard[],
): { cards: PlannerFieldCardPayloadRow[]; validationError: string | null } {
  const fieldCardMap = new Map<string, PlannerFieldCardPayloadRow>();
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const fieldLabel = row.fieldLabel.trim();
    const valueOptions = mergeOptionValues(
      plannerSplitMultiValue(row.valueOptionsText || '').map((value) => value.trim()),
    );
    if (!fieldLabel && valueOptions.length) {
      return {
        cards: [],
        validationError: 'Add a field name before saving variable values.',
      };
    }
    const resolvedLabel = fieldLabel || humanizePlannerCode(row.fieldCode || '');
    const fieldCode = normalizePlannerCode(row.fieldCode || resolvedLabel);
    if (!fieldCode || !resolvedLabel) {
      continue;
    }
    const existing = fieldCardMap.get(fieldCode);
    if (existing) {
      fieldCardMap.set(fieldCode, {
        ...existing,
        field_label: resolvedLabel,
        value_options: mergeOptionValues(existing.value_options, valueOptions),
        sort_order: Math.min(existing.sort_order, index),
      });
      continue;
    }
    fieldCardMap.set(fieldCode, {
      field_code: fieldCode,
      field_label: resolvedLabel,
      value_options: valueOptions,
      sort_order: index,
    });
  }
  return {
    cards: Array.from(fieldCardMap.values()).sort((a, b) => a.sort_order - b.sort_order),
    validationError: null,
  };
}

function isPlannerFieldCardsEndpointInactive(
  responseOk: boolean,
  responseStatus: number,
  payload: unknown,
) {
  if (payload && typeof payload === 'object' && Array.isArray((payload as { field_cards?: unknown }).field_cards)) {
    return false;
  }
  const payloadObj = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : {};
  const errorText = typeof payloadObj.error === 'string' ? payloadObj.error.toLowerCase() : '';
  if (
    errorText.includes('unknown action') ||
    errorText.includes('save_field_cards') ||
    errorText.includes('endpoint') ||
    errorText.includes('not active')
  ) {
    return true;
  }
  if (responseOk && !('field_cards' in payloadObj)) {
    return true;
  }
  if ((responseStatus === 404 || responseStatus === 405) && !('field_cards' in payloadObj)) {
    return true;
  }
  return false;
}

function plannerConfigForSection(section: PlannerSectionCode | null) {
  if (!section) return null;
  return PLANNER_SECTION_CHOICES.find((row) => row.code === section) || null;
}

function plannerGroupConfig(section: PlannerSectionCode | null, groupCode: string) {
  const sectionConfig = plannerConfigForSection(section);
  if (!sectionConfig) return null;
  return sectionConfig.groups.find((group) => group.code === groupCode) || null;
}

function plannerItemLabel(section: PlannerSectionCode | null, groupCode: string, itemCode: string) {
  const group = plannerGroupConfig(section, groupCode);
  if (!group || !itemCode) return '';
  const match = group.itemOptions?.find((option) => option.code === itemCode);
  return match ? match.label : itemCode.replace(/[_-]+/g, ' ');
}

function plannerFieldsForSelection(
  section: PlannerSectionCode | null,
  groupCode: string,
  itemCode: string,
) {
  const group = plannerGroupConfig(section, groupCode);
  if (!group) {
    return [] as PlannerFieldConfig[];
  }
  const option = group.itemOptions?.find((row) => row.code === itemCode);
  if (option?.fields?.length) {
    return option.fields;
  }
  return group.fields || [];
}

const Tab = createBottomTabNavigator<RootTabParamList>();

type NativeListItemProps = {
  title: string;
  subtitle?: string;
  meta?: string;
  onPress?: () => void;
  onLongPress?: () => void;
  rightSlot?: ReactNode;
  disabled?: boolean;
  dimmed?: boolean;
};

function NativeListItem({
  title,
  subtitle,
  meta,
  onPress,
  onLongPress,
  rightSlot,
  disabled = false,
  dimmed = false,
}: NativeListItemProps) {
  const isInteractive = !!onPress || !!onLongPress;
  return (
    <Pressable
      style={({ pressed }) => [
        styles.nativeListRow,
        isInteractive && pressed && styles.nativeListRowPressed,
        dimmed && styles.nativeListRowDimmed,
      ]}
      onPress={onPress}
      onLongPress={onLongPress}
      disabled={disabled || !isInteractive}
    >
      <View style={styles.nativeListRowBody}>
        <Text style={styles.nativeListRowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.nativeListRowSubtitle}>{subtitle}</Text> : null}
        {meta ? <Text style={styles.nativeListRowMeta}>{meta}</Text> : null}
      </View>
      <View style={styles.nativeListRowRight}>{rightSlot}</View>
    </Pressable>
  );
}

function EmptyTabScreen() {
  return null;
}

function renderMainTabIcon(name: keyof RootTabParamList, color: string, size: number) {
  if (name === 'Estimates') return <FileText size={size} color={color} />;
  if (name === 'Shopping') return <ShoppingBag size={size} color={color} />;
  if (name === 'Planner') return <CalendarCheck2 size={size} color={color} />;
  if (name === 'Expenses') return <ReceiptText size={size} color={color} />;
  return <Users size={size} color={color} />;
}

function AppShell() {
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 300);

  const [booting, setBooting] = useState(true);
  const [loggingIn, setLoggingIn] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_BASE_URL);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [token, setToken] = useState('');
  const [mainTab, setMainTab] = useState<MainTab>('estimates');
  const [menuOpen, setMenuOpen] = useState(false);
  const [estimates, setEstimates] = useState<EstimateRow[]>([]);
  const [selectedEstimate, setSelectedEstimate] = useState<EstimateRow | null>(null);
  const [estimateComposerOpen, setEstimateComposerOpen] = useState(false);
  const [creatingEstimate, setCreatingEstimate] = useState(false);
  const [newEstimateCustomer, setNewEstimateCustomer] = useState('');
  const [newEstimateEventType, setNewEstimateEventType] = useState('Event');
  const [newEstimateDate, setNewEstimateDate] = useState('');
  const [newEstimateLocation, setNewEstimateLocation] = useState('');
  const [newEstimateAdults, setNewEstimateAdults] = useState('');
  const [newEstimateKids, setNewEstimateKids] = useState('');
  const [newEstimateCatererId, setNewEstimateCatererId] = useState<number | null>(null);
  const [estimateBuilderOpen, setEstimateBuilderOpen] = useState(false);
  const [estimateBuilderLoading, setEstimateBuilderLoading] = useState(false);
  const [estimateBuilderSaving, setEstimateBuilderSaving] = useState(false);
  const [estimateBuilderStep, setEstimateBuilderStep] = useState<EstimateBuilderStep>('customer');
  const [estimateBuilderEstimate, setEstimateBuilderEstimate] = useState<EstimateBuilderEstimate | null>(null);
  const [estimateBuilderCatalog, setEstimateBuilderCatalog] = useState<EstimateBuilderCatalog | null>(null);
  const [estimateBuilderMenuChoices, setEstimateBuilderMenuChoices] = useState<EstimateBuilderMenuChoice[]>([]);
  const [estimateBuilderExtraLines, setEstimateBuilderExtraLines] = useState<EstimateBuilderExtraLine[]>([]);
  const [estimateBuilderMealPlanInput, setEstimateBuilderMealPlanInput] = useState('');
  const [estimateBuilderActiveMeal, setEstimateBuilderActiveMeal] = useState('');
  const [estimateBuilderMealOverrideDrafts, setEstimateBuilderMealOverrideDrafts] = useState<
    Record<string, EstimateBuilderMealOverrideDraft>
  >({});
  const [estimateBuilderMenuSearch, setEstimateBuilderMenuSearch] = useState('');
  const [estimateBuilderExtrasSearch, setEstimateBuilderExtrasSearch] = useState('');
  const [generatingPrintPdf, setGeneratingPrintPdf] = useState(false);
  const [savedEntries, setSavedEntries] = useState<SavedEntry[]>([]);
  const [staffRoleOptions, setStaffRoleOptions] = useState<StaffRoleOption[]>([]);
  const [staffEntries, setStaffEntries] = useState<StaffEntry[]>([]);
  const [staffTotalCost, setStaffTotalCost] = useState('0.00');
  const [unappliedStaffCost, setUnappliedStaffCost] = useState('0.00');
  const [loadingStaff, setLoadingStaff] = useState(false);
  const [applyingStaffCosts, setApplyingStaffCosts] = useState(false);
  const [activeQrRole, setActiveQrRole] = useState<StaffRoleOption | null>(null);
  const [shoppingLists, setShoppingLists] = useState<ShoppingListRow[]>([]);
  const [loadingShoppingLists, setLoadingShoppingLists] = useState(false);
  const [creatingShoppingList, setCreatingShoppingList] = useState(false);
  const [selectedShoppingList, setSelectedShoppingList] = useState<ShoppingListRow | null>(null);
  const [shoppingItems, setShoppingItems] = useState<ShoppingItem[]>([]);
  const [loadingShoppingItems, setLoadingShoppingItems] = useState(false);
  const [shoppingCatalogCategories, setShoppingCatalogCategories] = useState<ShoppingCatalogCategory[]>([]);
  const [loadingShoppingCatalog, setLoadingShoppingCatalog] = useState(false);
  const [addingShoppingItem, setAddingShoppingItem] = useState(false);
  const [removingShoppingItemId, setRemovingShoppingItemId] = useState<number | null>(null);
  const [deletingShoppingListId, setDeletingShoppingListId] = useState<number | null>(null);
  const [shoppingListTitle, setShoppingListTitle] = useState('');
  const [shoppingCatererId, setShoppingCatererId] = useState<number | null>(null);
  const [shoppingEstimateRefId, setShoppingEstimateRefId] = useState<number | null>(null);
  const [shoppingListScreenMode, setShoppingListScreenMode] = useState<'manage' | 'list'>('manage');
  const [showEstimatePicker, setShowEstimatePicker] = useState(false);
  const [savedItemSearchText, setSavedItemSearchText] = useState('');
  const [savedItemExpandedKey, setSavedItemExpandedKey] = useState<string | null>(null);
  const [savedItemQuickQty, setSavedItemQuickQty] = useState('1');
  const [savedItemQuickUnit, setSavedItemQuickUnit] = useState('');
  const [savedItemQuickType, setSavedItemQuickType] = useState('');
  const [savedItemQuickUnitPickerOpen, setSavedItemQuickUnitPickerOpen] = useState(false);
  const [savedItemLastQtyByKey, setSavedItemLastQtyByKey] = useState<Record<string, string>>({});
  const [shoppingItemEditorOpen, setShoppingItemEditorOpen] = useState(false);
  const [shoppingEditingItemId, setShoppingEditingItemId] = useState<number | null>(null);
  const [shoppingEditName, setShoppingEditName] = useState('');
  const [shoppingEditType, setShoppingEditType] = useState('');
  const [shoppingEditQty, setShoppingEditQty] = useState('');
  const [shoppingEditUnit, setShoppingEditUnit] = useState('');
  const [savingShoppingEdit, setSavingShoppingEdit] = useState(false);
  const [openCatalogCategory, setOpenCatalogCategory] = useState<string | null>(null);
  const [selectedPlannerEstimate, setSelectedPlannerEstimate] = useState<EstimateRow | null>(null);
  const [plannerSection, setPlannerSection] = useState<PlannerSectionCode | null>(null);
  const [plannerCategoryCode, setPlannerCategoryCode] = useState('');
  const [plannerEntries, setPlannerEntries] = useState<PlannerEntryRow[]>([]);
  const [plannerMemory, setPlannerMemory] = useState<PlannerMemoryBucket[]>([]);
  const [plannerItemCatalog, setPlannerItemCatalog] = useState<PlannerCatalogItem[]>([]);
  const [plannerIconOverrides, setPlannerIconOverrides] = useState<PlannerIconOverride[]>([]);
  const [plannerFieldCards, setPlannerFieldCards] = useState<PlannerFieldCardRow[]>([]);
  const [loadingPlanner, setLoadingPlanner] = useState(false);
  const [savingPlanner, setSavingPlanner] = useState(false);
  const [plannerSearchText, setPlannerSearchText] = useState('');
  const [plannerEditorVisible, setPlannerEditorVisible] = useState(false);
  const [plannerEditingEntryId, setPlannerEditingEntryId] = useState<number | null>(null);
  const [plannerEditorGroupCode, setPlannerEditorGroupCode] = useState('');
  const [plannerEditorItemCode, setPlannerEditorItemCode] = useState('');
  const [plannerEditorValues, setPlannerEditorValues] = useState<Record<string, string>>({});
  const [plannerEditorFieldDraftValues, setPlannerEditorFieldDraftValues] = useState<
    Record<string, string>
  >({});
  const [plannerEditorNotes, setPlannerEditorNotes] = useState('');
  const [plannerEditorChecked, setPlannerEditorChecked] = useState(false);
  const [plannerEditorFieldCards, setPlannerEditorFieldCards] = useState<PlannerEditorFieldCard[]>([]);
  const [plannerFieldCardsManagerOpen, setPlannerFieldCardsManagerOpen] = useState(false);
  const [plannerNewOptionName, setPlannerNewOptionName] = useState('');
  const tabNavigationRef = useRef<NavigationContainerRef<RootTabParamList> | null>(null);
  const savedItemSearchInputRef = useRef<TextInput | null>(null);

  const [drafts, setDrafts] = useState<ExpenseDraft[]>([]);
  const [activeRecordingDraftId, setActiveRecordingDraftId] = useState<string | null>(null);
  const [recordingPhotoUri, setRecordingPhotoUri] = useState<string | null>(null);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);

  const isRecording = !!recorderState.isRecording;

  const authFetchJson = useCallback(
    async (
      path: string,
      init: RequestInit,
      overrideToken?: string,
      overrideBaseUrl?: string,
    ) => {
      const activeToken = overrideToken ?? token;
      const activeBase = normalizeBaseUrl(overrideBaseUrl ?? apiBaseUrl);
      const headers = {
        ...(init.headers ?? {}),
        Authorization: `Bearer ${activeToken}`,
      };
      const response = await fetch(apiUrl(activeBase, path), {
        ...init,
        headers,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        const error = new Error(payload.error || `Request failed (${response.status})`) as ApiRequestError;
        error.status = response.status;
        throw error;
      }
      return payload;
    },
    [apiBaseUrl, token],
  );

  const loadEstimates = useCallback(
    async (overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingJobs(true);
      try {
        const payload = await authFetchJson(
          '/api/xpenz/estimates/',
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        setEstimates(Array.isArray(payload.estimates) ? payload.estimates : []);
      } finally {
        setLoadingJobs(false);
      }
    },
    [authFetchJson],
  );

  const loadEntries = useCallback(
    async (estimateId: number, overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingEntries(true);
      try {
        const payload = await authFetchJson(
          `/api/xpenz/estimates/${estimateId}/expenses/`,
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        setSavedEntries(Array.isArray(payload.entries) ? payload.entries : []);
      } finally {
        setLoadingEntries(false);
      }
    },
    [authFetchJson],
  );

  const loadStaffSummary = useCallback(
    async (estimateId: number, overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingStaff(true);
      try {
        const payload = await authFetchJson(
          `/api/xpenz/estimates/${estimateId}/staff/`,
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        setStaffRoleOptions(Array.isArray(payload.roles) ? payload.roles : []);
        setStaffEntries(Array.isArray(payload.entries) ? payload.entries : []);
        setStaffTotalCost(payload.total_staff_cost || '0.00');
        setUnappliedStaffCost(payload.unapplied_staff_cost || '0.00');
      } finally {
        setLoadingStaff(false);
      }
    },
    [authFetchJson],
  );

  const loadShoppingLists = useCallback(
    async (overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingShoppingLists(true);
      try {
        const payload = await authFetchJson(
          '/api/xpenz/shopping-lists/',
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        setShoppingLists(Array.isArray(payload.lists) ? payload.lists : []);
      } finally {
        setLoadingShoppingLists(false);
      }
    },
    [authFetchJson],
  );

  const loadShoppingListDetail = useCallback(
    async (
      shoppingListId: number,
      overrideToken?: string,
      overrideBaseUrl?: string,
      silent = false,
    ) => {
      if (!silent) {
        setLoadingShoppingItems(true);
      }
      try {
        const payload = await authFetchJson(
          `/api/xpenz/shopping-lists/${shoppingListId}/`,
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        if (payload.shopping_list) {
          setSelectedShoppingList(payload.shopping_list);
        }
        setShoppingItems(Array.isArray(payload.items) ? payload.items : []);
      } finally {
        if (!silent) {
          setLoadingShoppingItems(false);
        }
      }
    },
    [authFetchJson],
  );

  const loadShoppingListChanges = useCallback(
    async (
      shoppingListId: number,
      sinceCursor: string,
      timeoutSeconds = 25,
    ) => {
      const params = new URLSearchParams();
      if (sinceCursor) {
        params.set('since', sinceCursor);
      }
      params.set('timeout', String(timeoutSeconds));
      const payload = await authFetchJson(
        `/api/xpenz/shopping-lists/${shoppingListId}/changes/?${params.toString()}`,
        { method: 'GET' },
      );
      return payload;
    },
    [authFetchJson],
  );

  const loadShoppingCatalog = useCallback(
    async (overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingShoppingCatalog(true);
      try {
        const payload = await authFetchJson(
          '/api/xpenz/shopping-catalog/',
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        const categories: ShoppingCatalogCategory[] = Array.isArray(payload.categories)
          ? payload.categories
          : [];
        setShoppingCatalogCategories(categories);
        setOpenCatalogCategory((prev) => {
          if (prev && categories.some((category) => category.category === prev)) return prev;
          return null;
        });
      } finally {
        setLoadingShoppingCatalog(false);
      }
    },
    [authFetchJson],
  );

  const loadPlannerData = useCallback(
    async (estimateId: number, overrideToken?: string, overrideBaseUrl?: string) => {
      setLoadingPlanner(true);
      try {
        const payload = await authFetchJson(
          `/api/xpenz/estimates/${estimateId}/planner/`,
          { method: 'GET' },
          overrideToken,
          overrideBaseUrl,
        );
        setPlannerEntries(Array.isArray(payload.entries) ? payload.entries : []);
        setPlannerMemory(Array.isArray(payload.memory) ? payload.memory : []);
        setPlannerItemCatalog(Array.isArray(payload.item_catalog) ? payload.item_catalog : []);
        setPlannerIconOverrides(Array.isArray(payload.icon_overrides) ? payload.icon_overrides : []);
        setPlannerFieldCards(Array.isArray(payload.field_cards) ? payload.field_cards : []);
      } finally {
        setLoadingPlanner(false);
      }
    },
    [authFetchJson],
  );

  const catererChoices = useMemo(() => {
    const map = new Map<number, string>();
    for (const estimate of estimates) {
      map.set(estimate.caterer_id, estimate.caterer_name);
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [estimates]);

  const selectedEstimateReference = useMemo(
    () => estimates.find((estimate) => estimate.id === shoppingEstimateRefId) || null,
    [estimates, shoppingEstimateRefId],
  );

  const shoppingCatalogItemsFlat = useMemo(() => {
    const rows: ShoppingCatalogListItem[] = [];
    for (const category of shoppingCatalogCategories) {
      for (const item of category.items) {
        rows.push({
          ...item,
          category: category.category,
          category_label: category.category_label,
        });
      }
    }
    return rows;
  }, [shoppingCatalogCategories]);

  const shoppingCatalogListItemByName = useMemo(() => {
    const index = new Map<string, ShoppingCatalogListItem>();
    for (const item of shoppingCatalogItemsFlat) {
      const key = item.item_name.trim().toLowerCase();
      if (!key || index.has(key)) continue;
      index.set(key, item);
    }
    return index;
  }, [shoppingCatalogItemsFlat]);

  const shoppingSections = useMemo(() => {
    const grouped = new Map<string, { label: string; items: ShoppingItem[] }>();
    for (const item of shoppingItems) {
      if (!grouped.has(item.category)) {
        grouped.set(item.category, { label: item.category_label, items: [] });
      }
      grouped.get(item.category)?.items.push(item);
    }
    return Array.from(grouped.values());
  }, [shoppingItems]);

  const shoppingAllUnitOptions = useMemo(() => {
    const fromCatalog = shoppingCatalogItemsFlat.flatMap((item) => item.unit_options || []);
    return mergeOptionValues(DEFAULT_SHOPPING_UNIT_OPTIONS, fromCatalog, [savedItemQuickUnit]);
  }, [savedItemQuickUnit, shoppingCatalogItemsFlat]);

  const recentSavedItems = useMemo(() => {
    const sorted = [...shoppingItems].sort(
      (left, right) =>
        new Date(right.created_at || '').getTime() - new Date(left.created_at || '').getTime(),
    );
    const seen = new Set<string>();
    const rows: ShoppingCatalogListItem[] = [];
    for (const row of sorted) {
      const key = (row.item_name || '').trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const catalog = shoppingCatalogListItemByName.get(key);
      if (catalog) {
        rows.push(catalog);
      } else {
        rows.push({
          item_name: row.item_name,
          category: row.category,
          category_label: row.category_label,
          type_options: row.item_type ? [row.item_type] : [],
          unit_options: row.item_unit ? [row.item_unit] : [],
          last_used_unit: row.item_unit || '',
          usage_count: 0,
        });
      }
      if (rows.length >= 8) break;
    }
    return rows;
  }, [shoppingCatalogListItemByName, shoppingItems]);

  const frequentSavedItems = useMemo(() => {
    const seen = new Set<string>();
    return [...shoppingCatalogItemsFlat]
      .sort((left, right) => {
        if (right.usage_count !== left.usage_count) {
          return right.usage_count - left.usage_count;
        }
        return left.item_name.localeCompare(right.item_name);
      })
      .filter((item) => {
        const key = item.item_name.trim().toLowerCase();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 10);
  }, [shoppingCatalogItemsFlat]);

  const filteredSavedItems = useMemo(() => {
    const query = savedItemSearchText.trim().toLowerCase();
    if (!query) return [] as ShoppingCatalogListItem[];
    const starts: ShoppingCatalogListItem[] = [];
    const includes: ShoppingCatalogListItem[] = [];
    for (const item of shoppingCatalogItemsFlat) {
      const name = item.item_name.trim().toLowerCase();
      if (!name.includes(query)) continue;
      if (name.startsWith(query)) {
        starts.push(item);
      } else {
        includes.push(item);
      }
    }
    const seen = new Set<string>();
    return [...starts, ...includes].filter((item) => {
      const key = item.item_name.trim().toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [savedItemSearchText, shoppingCatalogItemsFlat]);

  const hasExactSavedItemMatch = useMemo(() => {
    const query = savedItemSearchText.trim().toLowerCase();
    if (!query) return true;
    return shoppingCatalogListItemByName.has(query);
  }, [savedItemSearchText, shoppingCatalogListItemByName]);

  const quickAddExpandedItem = useMemo(() => {
    if (!savedItemExpandedKey || savedItemExpandedKey === '__new__') return null;
    return shoppingCatalogListItemByName.get(savedItemExpandedKey) || null;
  }, [savedItemExpandedKey, shoppingCatalogListItemByName]);

  const expandedItemInRecent = useMemo(() => {
    if (!savedItemExpandedKey || savedItemExpandedKey === '__new__') return false;
    return recentSavedItems.some(
      (item) => item.item_name.trim().toLowerCase() === savedItemExpandedKey,
    );
  }, [recentSavedItems, savedItemExpandedKey]);

  const frequentExpandedItem = useMemo(() => {
    if (!savedItemExpandedKey || savedItemExpandedKey === '__new__') return null;
    return (
      frequentSavedItems.find(
        (item) => item.item_name.trim().toLowerCase() === savedItemExpandedKey,
      ) || null
    );
  }, [frequentSavedItems, savedItemExpandedKey]);

  const quickAddUnitOptions = useMemo(
    () =>
      mergeOptionValues(
        DEFAULT_SHOPPING_UNIT_OPTIONS,
        quickAddExpandedItem?.unit_options || [],
        shoppingAllUnitOptions,
        [savedItemQuickUnit],
      ),
    [quickAddExpandedItem?.unit_options, savedItemQuickUnit, shoppingAllUnitOptions],
  );

  const estimateBuilderMealPlan = useMemo(
    () => parseMealPlanInput(estimateBuilderMealPlanInput),
    [estimateBuilderMealPlanInput],
  );

  const estimateBuilderMenuChoiceMap = useMemo(() => {
    const map = new Map<string, EstimateBuilderMenuChoice>();
    for (const row of estimateBuilderMenuChoices) {
      const mealName = (row.meal_name || '').trim();
      if (!row.menu_item_id || !mealName) {
        continue;
      }
      map.set(`${row.menu_item_id}|${mealName.toLowerCase()}`, row);
    }
    return map;
  }, [estimateBuilderMenuChoices]);

  const estimateBuilderExtraLineMap = useMemo(() => {
    const map = new Map<number, EstimateBuilderExtraLine>();
    for (const row of estimateBuilderExtraLines) {
      if (!row.extra_item_id) {
        continue;
      }
      map.set(row.extra_item_id, row);
    }
    return map;
  }, [estimateBuilderExtraLines]);

  useEffect(() => {
    if (!estimateBuilderOpen) {
      return;
    }
    if (!estimateBuilderMealPlan.length) {
      setEstimateBuilderActiveMeal('Signature Menu');
      return;
    }
    if (
      estimateBuilderActiveMeal &&
      estimateBuilderMealPlan.some(
        (name) => name.toLowerCase() === estimateBuilderActiveMeal.toLowerCase(),
      )
    ) {
      return;
    }
    setEstimateBuilderActiveMeal(estimateBuilderMealPlan[0]);
  }, [estimateBuilderActiveMeal, estimateBuilderMealPlan, estimateBuilderOpen]);

  const plannerMemoryMap = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const bucket of plannerMemory) {
      const exact = `${bucket.section}|${bucket.group_code || ''}|${bucket.item_code || ''}|${bucket.field_code || ''}`;
      map.set(exact, bucket.values || []);
    }
    return map;
  }, [plannerMemory]);

  const plannerIconOverrideMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of plannerIconOverrides) {
      const section = row.section;
      const groupCode = (row.group_code || '').trim();
      const itemCode = (row.item_code || '').trim();
      const iconKey = (row.icon_key || '').trim();
      if (!section || !groupCode || !iconKey) {
        continue;
      }
      map.set(`${section}|${groupCode}|${itemCode}`, iconKey);
    }
    return map;
  }, [plannerIconOverrides]);

  const plannerFieldCardMap = useMemo(() => {
    const map = new Map<string, PlannerFieldCardRow[]>();
    for (const row of plannerFieldCards) {
      const section = row.section;
      const groupCode = (row.group_code || '').trim();
      const itemCode = (row.item_code || '').trim();
      const fieldCode = (row.field_code || '').trim();
      if (!section || !groupCode || !fieldCode) {
        continue;
      }
      const key = `${section}|${groupCode}|${itemCode}`;
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)?.push(row);
    }
    for (const [key, rows] of map.entries()) {
      rows.sort(
        (a, b) =>
          (a.sort_order || 0) - (b.sort_order || 0) ||
          (a.field_label || '').localeCompare(b.field_label || ''),
      );
      map.set(key, rows);
    }
    return map;
  }, [plannerFieldCards]);

  const plannerSectionChoices = useMemo(() => {
    const fieldsByItem = new Map<string, Set<string>>();
    const toFieldConfig = (
      fieldCode: string,
      overrideLabel = '',
      overrideValueOptions?: string[],
    ): PlannerFieldConfig => {
      const template = PLANNER_FIELD_TEMPLATE_MAP.get(fieldCode);
      const fallbackLabel = overrideLabel || humanizePlannerCode(fieldCode);
      if (template) {
        return {
          ...template,
          label: overrideLabel || template.label,
          placeholder: overrideLabel || template.placeholder || template.label,
          valueOptions: mergeOptionValues(template.valueOptions, overrideValueOptions),
        };
      }
      return {
        code: fieldCode,
        label: fallbackLabel,
        placeholder: fallbackLabel,
        valueOptions: mergeOptionValues(overrideValueOptions),
      };
    };
    const mergeFieldConfigs = (
      baseFields: PlannerFieldConfig[] | undefined,
      extraCodes: string[],
      cardRows: PlannerFieldCardRow[],
    ) => {
      const mergedFields: PlannerFieldConfig[] = (baseFields || []).map((field) => ({ ...field }));
      const seen = new Set(mergedFields.map((field) => field.code));
      const byCode = new Map<string, number>();
      mergedFields.forEach((field, index) => byCode.set(field.code, index));

      for (const card of cardRows) {
        const fieldCode = (card.field_code || '').trim();
        if (!fieldCode) {
          continue;
        }
        const label = (card.field_label || '').trim();
        const cardOptions = mergeOptionValues(card.value_options || []);
        if (byCode.has(fieldCode)) {
          const index = byCode.get(fieldCode) || 0;
          mergedFields[index] = {
            ...mergedFields[index],
            label: label || mergedFields[index].label,
            placeholder: label || mergedFields[index].placeholder || mergedFields[index].label,
            valueOptions: mergeOptionValues(mergedFields[index].valueOptions, cardOptions),
          };
          continue;
        }
        seen.add(fieldCode);
        mergedFields.push(toFieldConfig(fieldCode, label, cardOptions));
      }

      const sortedCodes = [...extraCodes].sort();
      for (const fieldCode of sortedCodes) {
        if (!fieldCode || seen.has(fieldCode)) {
          continue;
        }
        seen.add(fieldCode);
        mergedFields.push(toFieldConfig(fieldCode));
      }
      return mergedFields;
    };

    for (const bucket of plannerMemory) {
      const section = bucket.section;
      const groupCode = (bucket.group_code || '').trim();
      const itemCode = (bucket.item_code || '').trim();
      const fieldCode = (bucket.field_code || '').trim();
      if (!section || !groupCode || !fieldCode) {
        continue;
      }
      const key = `${section}|${groupCode}|${itemCode}`;
      if (!fieldsByItem.has(key)) {
        fieldsByItem.set(key, new Set<string>());
      }
      fieldsByItem.get(key)?.add(fieldCode);
    }

    const catalogByGroup = new Map<string, PlannerCatalogItem[]>();
    for (const row of plannerItemCatalog) {
      const section = row.section;
      const groupCode = (row.group_code || '').trim();
      const itemCode = (row.item_code || '').trim();
      if (!section || !groupCode || !itemCode) {
        continue;
      }
      const key = `${section}|${groupCode}`;
      if (!catalogByGroup.has(key)) {
        catalogByGroup.set(key, []);
      }
      catalogByGroup.get(key)?.push(row);
    }

    return PLANNER_SECTION_CHOICES.map((section) => {
      const groups = section.groups.map((group) => {
        const groupKey = `${section.code}|${group.code}|`;
        const groupFields = mergeFieldConfigs(
          group.fields,
          Array.from(fieldsByItem.get(groupKey) || []),
          plannerFieldCardMap.get(groupKey) || [],
        );
        const baseOptions = (group.itemOptions || []).map((option) => {
          const optionKey = `${section.code}|${group.code}|${option.code}`;
          const optionFields = mergeFieldConfigs(
            option.fields?.length ? option.fields : groupFields,
            Array.from(fieldsByItem.get(optionKey) || []),
            plannerFieldCardMap.get(optionKey) || [],
          );
          return {
            ...option,
            fields: optionFields.length ? optionFields : undefined,
          };
        });
        const seenCodes = new Set(baseOptions.map((option) => option.code));
        const dynamicOptions: PlannerItemOption[] = [];
        const rows = catalogByGroup.get(`${section.code}|${group.code}`) || [];
        for (const row of rows) {
          const itemCode = (row.item_code || '').trim();
          if (!itemCode || seenCodes.has(itemCode)) {
            continue;
          }
          seenCodes.add(itemCode);
          const itemKey = `${section.code}|${group.code}|${itemCode}`;
          const fields = mergeFieldConfigs(
            groupFields,
            Array.from(fieldsByItem.get(itemKey) || []),
            plannerFieldCardMap.get(itemKey) || [],
          );
          dynamicOptions.push({
            code: itemCode,
            label: (row.item_label || '').trim() || humanizePlannerCode(itemCode),
            fields: fields.length ? fields : undefined,
          });
        }
        const mergedOptions = [...baseOptions, ...dynamicOptions];
        if (!mergedOptions.length) {
          return group;
        }
        return {
          ...group,
          fields: groupFields,
          itemOptions: mergedOptions,
          showGroupCard: !(group.itemOptions?.length),
        };
      });
      return {
        ...section,
        groups,
      };
    });
  }, [plannerFieldCardMap, plannerItemCatalog, plannerMemory]);

  const plannerConfigForActive = useCallback(
    (section: PlannerSectionCode | null) => {
      if (!section) return null;
      return plannerSectionChoices.find((row) => row.code === section) || null;
    },
    [plannerSectionChoices],
  );

  const plannerGroupForActive = useCallback(
    (section: PlannerSectionCode | null, groupCode: string) => {
      const sectionConfig = plannerConfigForActive(section);
      if (!sectionConfig) return null;
      return sectionConfig.groups.find((group) => group.code === groupCode) || null;
    },
    [plannerConfigForActive],
  );

  const plannerFieldsForActive = useCallback(
    (
      section: PlannerSectionCode | null,
      groupCode: string,
      itemCode: string,
    ) => {
      const group = plannerGroupForActive(section, groupCode);
      if (!group) {
        return [] as PlannerFieldConfig[];
      }
      const option = group.itemOptions?.find((row) => row.code === itemCode);
      if (option?.fields?.length) {
        return option.fields;
      }
      return group.fields || [];
    },
    [plannerGroupForActive],
  );

  const plannerEntriesForSection = useMemo(() => {
    if (!plannerSection) return [];
    return plannerEntries.filter((entry) => entry.section === plannerSection);
  }, [plannerEntries, plannerSection]);

  const buildPlannerSummary = useCallback((entries: PlannerEntryRow[]) => {
    if (!entries.length) {
      return [] as string[];
    }

    const summaryLines: string[] = [];
    const primary = entries[0];
    const readDataValue = (entry: PlannerEntryRow, key: string) =>
      ((entry.data || {})[key] || '').toString().trim();

    const firstDescriptorValue = (entry: PlannerEntryRow) => {
      const preferredCodes = ['type', 'item', 'item_name', 'name', 'style', 'feature', 'size', 'color'];
      for (const code of preferredCodes) {
        const raw = readDataValue(entry, code);
        if (raw) {
          return raw;
        }
      }
      for (const row of entry.data_rows || []) {
        const fieldCode = normalizePlannerCode(row.field_code || row.field_label || '');
        if (!fieldCode || fieldCode === 'qty' || fieldCode === 'quantity' || fieldCode === 'supplier' || fieldCode === 'notes') {
          continue;
        }
        const value = (row.value || '').trim();
        if (value) {
          return value;
        }
      }
      return (entry.item_label || '').trim();
    };

    if (entries.length > 1) {
      summaryLines.push(`${entries.length} entries saved`);
    }

    if (primary.section === 'ORDERS' && entries.length > 1) {
      const supplierBuckets = new Map<string, { supplier: string; rows: PlannerEntryRow[] }>();
      for (const entry of entries) {
        const supplier = readDataValue(entry, 'supplier') || 'No supplier';
        const key = supplier.toLowerCase();
        const existing = supplierBuckets.get(key);
        if (existing) {
          existing.rows.push(entry);
          continue;
        }
        supplierBuckets.set(key, { supplier, rows: [entry] });
      }

      for (const bucket of supplierBuckets.values()) {
        summaryLines.push(`Supplier - ${bucket.supplier}`);
        for (const entry of bucket.rows) {
          const descriptor = firstDescriptorValue(entry);
          const qty = readDataValue(entry, 'qty') || readDataValue(entry, 'quantity');
          if (descriptor && qty) {
            summaryLines.push(`• ${descriptor}: ${qty}`);
          } else if (descriptor) {
            summaryLines.push(`• ${descriptor}`);
          } else if (qty) {
            summaryLines.push(`• Qty: ${qty}`);
          } else {
            summaryLines.push('• Entry');
          }
        }
      }
      return summaryLines;
    }

    if (entries.length === 1) {
      for (const row of primary.data_rows || []) {
        const value = (row.value || '').trim();
        if (!value) {
          continue;
        }
        summaryLines.push(`${row.field_label}: ${value}`);
      }
      if (primary.notes) {
        summaryLines.push(`Notes: ${primary.notes}`);
      }
      return summaryLines;
    }

    entries.forEach((entry, index) => {
      const lineParts: string[] = [];
      for (const row of entry.data_rows || []) {
        const value = (row.value || '').trim();
        if (!value || normalizePlannerCode(row.field_code || row.field_label || '') === 'notes') {
          continue;
        }
        lineParts.push(`${row.field_label}: ${value}`);
      }
      if (lineParts.length) {
        summaryLines.push(`${index + 1}. ${lineParts.join(' • ')}`);
      } else if (entry.notes) {
        summaryLines.push(`${index + 1}. Notes: ${entry.notes}`);
      } else {
        summaryLines.push(`${index + 1}. Entry`);
      }
    });
    return summaryLines;
  }, []);

  const plannerCategoryCards = useMemo(() => {
    if (!plannerSection) return [];
    const sectionConfig = plannerConfigForActive(plannerSection);
    if (!sectionConfig) return [];

    const cards: PlannerChecklistCard[] = [];
    const rowsByGroup = new Map<string, PlannerEntryRow[]>();
    for (const entry of plannerEntriesForSection) {
      if (!rowsByGroup.has(entry.group_code)) {
        rowsByGroup.set(entry.group_code, []);
      }
      rowsByGroup.get(entry.group_code)?.push(entry);
    }

    for (const group of sectionConfig.groups) {
      const groupEntries = rowsByGroup.get(group.code) || [];
      if (group.itemOptions?.length) {
        const addedOptionCount = group.itemOptions.filter((option) =>
          groupEntries.some((entry) => (entry.item_code || '') === option.code),
        ).length;
        const summaryLines = [
          `${addedOptionCount}/${group.itemOptions.length} options added`,
          ...buildPlannerSummary(groupEntries),
        ];
        cards.push({
          key: `${group.code}::`,
          groupCode: group.code,
          itemCode: '',
          label: group.label,
          icon:
            plannerIconOverrideMap.get(`${plannerSection}|${group.code}|`) ||
            PLANNER_ITEM_ICON_MAP[`${plannerSection}|${group.code}|`] ||
            'circle',
          isAdded: groupEntries.length > 0,
          isChecked: groupEntries.length > 0 && groupEntries.every((entry) => !!entry.is_checked),
          summaryLines,
          entries: groupEntries,
        });
      } else {
        const plainEntries = groupEntries.filter((entry) => !entry.item_code);
        const entriesToUse = plainEntries.length ? plainEntries : groupEntries;
        cards.push({
          key: `${group.code}::`,
          groupCode: group.code,
          itemCode: '',
          label: group.label,
          icon:
            plannerIconOverrideMap.get(`${plannerSection}|${group.code}|`) ||
            PLANNER_ITEM_ICON_MAP[`${plannerSection}|${group.code}|`] ||
            'circle',
          isAdded: entriesToUse.length > 0,
          isChecked: entriesToUse.length > 0 && entriesToUse.every((entry) => !!entry.is_checked),
          summaryLines: buildPlannerSummary(entriesToUse),
          entries: entriesToUse,
        });
      }
    }
    return cards;
  }, [
    buildPlannerSummary,
    plannerConfigForActive,
    plannerEntriesForSection,
    plannerIconOverrideMap,
    plannerSection,
  ]);

  const activePlannerCategory = useMemo(
    () => plannerGroupForActive(plannerSection, plannerCategoryCode),
    [plannerCategoryCode, plannerGroupForActive, plannerSection],
  );

  const plannerOptionCards = useMemo(() => {
    if (!plannerSection || !activePlannerCategory?.itemOptions?.length) {
      return [] as PlannerChecklistCard[];
    }
    const groupEntries = plannerEntriesForSection.filter(
      (entry) => entry.group_code === activePlannerCategory.code,
    );
    const cards: PlannerChecklistCard[] = [];
    for (const option of activePlannerCategory.itemOptions) {
      const optionEntries = groupEntries.filter((entry) => (entry.item_code || '') === option.code);
      cards.push({
        key: `${activePlannerCategory.code}::${option.code}`,
        groupCode: activePlannerCategory.code,
        itemCode: option.code,
        label: option.label,
        secondaryLabel: activePlannerCategory.label,
        icon:
          plannerIconOverrideMap.get(`${plannerSection}|${activePlannerCategory.code}|${option.code}`) ||
          plannerIconOverrideMap.get(`${plannerSection}|${activePlannerCategory.code}|`) ||
          PLANNER_ITEM_ICON_MAP[`${plannerSection}|${activePlannerCategory.code}|${option.code}`] ||
          PLANNER_ITEM_ICON_MAP[`${plannerSection}|${activePlannerCategory.code}|`] ||
          'circle',
        isAdded: optionEntries.length > 0,
        isChecked: optionEntries.length > 0 && optionEntries.every((entry) => !!entry.is_checked),
        summaryLines: buildPlannerSummary(optionEntries),
        entries: optionEntries,
      });
    }
    return cards;
  }, [
    activePlannerCategory,
    buildPlannerSummary,
    plannerEntriesForSection,
    plannerIconOverrideMap,
    plannerSection,
  ]);

  const filteredPlannerCategoryCards = useMemo(() => {
    const search = plannerSearchText.trim().toLowerCase();
    if (!search) {
      return plannerCategoryCards;
    }
    return plannerCategoryCards.filter((card) => {
      const haystack = [
        card.label,
        card.secondaryLabel || '',
        ...card.summaryLines,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(search);
    });
  }, [plannerCategoryCards, plannerSearchText]);

  const filteredPlannerOptionCards = useMemo(() => {
    const search = plannerSearchText.trim().toLowerCase();
    if (!search) {
      return plannerOptionCards;
    }
    return plannerOptionCards.filter((card) => {
      const haystack = [
        card.label,
        card.secondaryLabel || '',
        ...card.summaryLines,
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(search);
    });
  }, [plannerOptionCards, plannerSearchText]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [savedToken, savedBase, savedQtyDefaults] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          SecureStore.getItemAsync(BASE_URL_KEY),
          SecureStore.getItemAsync(SHOPPING_LAST_QTY_KEY),
        ]);
        if (savedQtyDefaults) {
          try {
            const parsed = JSON.parse(savedQtyDefaults) as Record<string, unknown>;
            const next: Record<string, string> = {};
            for (const [key, value] of Object.entries(parsed || {})) {
              if (typeof value === 'string') {
                next[key] = value;
              }
            }
            setSavedItemLastQtyByKey(next);
          } catch {
            // Ignore invalid local cache.
          }
        }
        if (savedBase) {
          setApiBaseUrl(savedBase);
        }
        if (savedToken && savedBase) {
          setToken(savedToken);
          await Promise.all([
            loadEstimates(savedToken, savedBase),
            loadShoppingLists(savedToken, savedBase),
            loadShoppingCatalog(savedToken, savedBase),
          ]);
        }
      } catch {
        await Promise.all([
          SecureStore.deleteItemAsync(TOKEN_KEY),
          SecureStore.deleteItemAsync(BASE_URL_KEY),
        ]);
        setToken('');
      } finally {
        setBooting(false);
      }
    }

    bootstrap();
  }, [loadEstimates, loadShoppingCatalog, loadShoppingLists]);

  useEffect(() => {
    SecureStore.setItemAsync(SHOPPING_LAST_QTY_KEY, JSON.stringify(savedItemLastQtyByKey)).catch(() => {
      // Ignore storage write failures and keep the in-memory defaults.
    });
  }, [savedItemLastQtyByKey]);

  useEffect(() => {
    if (shoppingEstimateRefId) {
      return;
    }
    if (catererChoices.length === 1) {
      setShoppingCatererId(catererChoices[0].id);
    }
  }, [catererChoices, shoppingEstimateRefId]);

  useEffect(() => {
    if (!token || mainTab !== 'shopping' || !selectedShoppingList?.id || selectedEstimate) {
      return;
    }
    let cancelled = false;
    const shoppingListId = selectedShoppingList.id;
    let cursor = selectedShoppingList.updated_at || '';

    async function loop() {
      while (!cancelled) {
        try {
          const payload = await loadShoppingListChanges(shoppingListId, cursor, 25);
          if (cancelled) {
            return;
          }
          if (payload.deleted || payload.shopping_list?.is_deleted) {
            setSelectedShoppingList(null);
            setShoppingItems([]);
            setSavedItemExpandedKey(null);
            setSavedItemQuickUnitPickerOpen(false);
            setShoppingListScreenMode('manage');
            await Promise.all([loadShoppingLists(), loadShoppingCatalog()]);
            return;
          }
          if (payload.shopping_list) {
            setSelectedShoppingList(payload.shopping_list);
            setShoppingLists((prev) =>
              prev.map((row) => (row.id === payload.shopping_list.id ? payload.shopping_list : row)),
            );
          }
          if (payload.changed && Array.isArray(payload.items)) {
            setShoppingItems(payload.items);
          }
          if (payload.cursor) {
            cursor = payload.cursor;
          } else if (payload.shopping_list?.updated_at) {
            cursor = payload.shopping_list.updated_at;
          }
        } catch (error) {
          if (cancelled) {
            return;
          }
          const status = (error as ApiRequestError | undefined)?.status;
          if (status === 404) {
            setSelectedShoppingList(null);
            setShoppingItems([]);
            setSavedItemExpandedKey(null);
            setSavedItemQuickUnitPickerOpen(false);
            setShoppingListScreenMode('manage');
            await Promise.all([loadShoppingLists(), loadShoppingCatalog()]);
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 1200));
        }
      }
    }

    loop();
    return () => {
      cancelled = true;
    };
  }, [
    loadShoppingCatalog,
    loadShoppingListChanges,
    loadShoppingLists,
    mainTab,
    selectedEstimate,
    selectedShoppingList?.id,
    token,
  ]);

  useEffect(() => {
    if (mainTab !== 'shopping' || !selectedShoppingList?.id || shoppingListScreenMode !== 'manage') {
      return;
    }
    const timer = setTimeout(() => {
      savedItemSearchInputRef.current?.focus();
    }, 120);
    return () => clearTimeout(timer);
  }, [mainTab, selectedShoppingList?.id, shoppingListScreenMode]);

  const handleLogin = useCallback(async () => {
    const cleanBase = normalizeBaseUrl(apiBaseUrl);
    if (!cleanBase || !username.trim() || !password) {
      Alert.alert('Missing fields', 'Add API URL, username/email, and password.');
      return;
    }

    setLoggingIn(true);
    try {
      const response = await fetch(apiUrl(cleanBase, '/api/xpenz/login/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false || !payload.token) {
        throw new Error(payload.error || 'Login failed.');
      }

      setToken(payload.token);
      await Promise.all([
        SecureStore.setItemAsync(TOKEN_KEY, payload.token),
        SecureStore.setItemAsync(BASE_URL_KEY, cleanBase),
      ]);
      await Promise.all([
        loadEstimates(payload.token, cleanBase),
        loadShoppingLists(payload.token, cleanBase),
        loadShoppingCatalog(payload.token, cleanBase),
      ]);
      setPassword('');
    } catch (error) {
      Alert.alert('Login error', error instanceof Error ? error.message : 'Unable to log in.');
    } finally {
      setLoggingIn(false);
    }
  }, [apiBaseUrl, loadEstimates, loadShoppingCatalog, loadShoppingLists, password, username]);

  const handleLogout = useCallback(async () => {
    try {
      await Promise.all([
        SecureStore.deleteItemAsync(TOKEN_KEY),
        SecureStore.deleteItemAsync(BASE_URL_KEY),
      ]);
    } finally {
      setToken('');
      setMainTab('estimates');
      setMenuOpen(false);
      setSelectedEstimate(null);
      setEstimateComposerOpen(false);
      setCreatingEstimate(false);
      setNewEstimateCustomer('');
      setNewEstimateEventType('Event');
      setNewEstimateDate('');
      setNewEstimateLocation('');
      setNewEstimateAdults('');
      setNewEstimateKids('');
      setNewEstimateCatererId(null);
      setEstimateBuilderOpen(false);
      setEstimateBuilderLoading(false);
      setEstimateBuilderSaving(false);
      setEstimateBuilderStep('customer');
      setEstimateBuilderEstimate(null);
      setEstimateBuilderCatalog(null);
      setEstimateBuilderMenuChoices([]);
      setEstimateBuilderExtraLines([]);
      setEstimateBuilderMealPlanInput('');
      setEstimateBuilderActiveMeal('');
      setEstimateBuilderMenuSearch('');
      setEstimateBuilderExtrasSearch('');
      setGeneratingPrintPdf(false);
      setEstimates([]);
      setSavedEntries([]);
      setStaffRoleOptions([]);
      setStaffEntries([]);
      setStaffTotalCost('0.00');
      setUnappliedStaffCost('0.00');
      setShoppingLists([]);
      setSelectedShoppingList(null);
      setShoppingItems([]);
      setShoppingCatalogCategories([]);
      setShoppingListTitle('');
      setShoppingCatererId(null);
      setShoppingEstimateRefId(null);
      setShoppingListScreenMode('manage');
      setDeletingShoppingListId(null);
      setShowEstimatePicker(false);
      setSavedItemSearchText('');
      setSavedItemExpandedKey(null);
      setSavedItemQuickQty('1');
      setSavedItemQuickUnit('');
      setSavedItemQuickType('');
      setSavedItemQuickUnitPickerOpen(false);
      setSavedItemLastQtyByKey({});
      setShoppingItemEditorOpen(false);
      setShoppingEditingItemId(null);
      setShoppingEditName('');
      setShoppingEditType('');
      setShoppingEditQty('');
      setShoppingEditUnit('');
      setSavingShoppingEdit(false);
      setOpenCatalogCategory(null);
      setSelectedPlannerEstimate(null);
      setPlannerSection(null);
      setPlannerCategoryCode('');
      setPlannerEntries([]);
      setPlannerMemory([]);
      setPlannerItemCatalog([]);
      setPlannerIconOverrides([]);
      setPlannerFieldCards([]);
      setPlannerSearchText('');
      setPlannerEditorVisible(false);
      setPlannerEditingEntryId(null);
      setPlannerEditorGroupCode('');
      setPlannerEditorItemCode('');
      setPlannerEditorValues({});
      setPlannerEditorFieldDraftValues({});
      setPlannerEditorNotes('');
      setPlannerEditorChecked(false);
      setPlannerEditorFieldCards([]);
      setPlannerFieldCardsManagerOpen(false);
      setPlannerNewOptionName('');
      setDrafts([]);
    }
  }, []);

  const handleSelectEstimate = useCallback(
    async (estimate: EstimateRow, targetTab: MainTab = 'expenses') => {
      if (targetTab === 'staff' && !estimate.can_manage_staff) {
        Alert.alert('No access', 'Your account cannot manage staff on this estimate.');
        return;
      }
      setSelectedEstimate(estimate);
      if (targetTab === 'expenses' || targetTab === 'staff') {
        setMainTab(targetTab);
        tabNavigationRef.current?.navigate(TAB_NAME_BY_MAIN[targetTab]);
      }
      setDrafts([]);
      try {
        await Promise.all([loadEntries(estimate.id), estimate.can_manage_staff ? loadStaffSummary(estimate.id) : Promise.resolve()]);
      } catch (error) {
        Alert.alert(
          'Load error',
          error instanceof Error ? error.message : 'Unable to load estimate entries.',
        );
      }
    },
    [loadEntries, loadStaffSummary],
  );

  const switchMainTab = useCallback((nextTab: MainTab, syncNavigation = false) => {
    setMainTab(nextTab);
    setMenuOpen(false);
    if (nextTab === 'estimates' || nextTab === 'shopping' || nextTab === 'planner') {
      setSelectedEstimate(null);
    }
    if (syncNavigation) {
      tabNavigationRef.current?.navigate(TAB_NAME_BY_MAIN[nextTab]);
    }
  }, []);

  const tabBarHeight = useMemo(() => TAB_BAR_HEIGHT + insets.bottom, [insets.bottom]);
  const modalTopInset = useMemo(() => Math.max(insets.top, 8), [insets.top]);
  const modalHeaderStyle = useMemo(
    () => [styles.plannerEditorHeader, { paddingTop: modalTopInset + 6 }],
    [modalTopInset],
  );
  const nativeTabHostStyle = useMemo(
    () => [styles.nativeTabHost, { height: tabBarHeight }],
    [tabBarHeight],
  );
  const nativeTabBarStyle = useMemo(
    () => [
      styles.nativeTabBar,
      {
        height: tabBarHeight,
      },
    ],
    [tabBarHeight],
  );
  const tabbedContentWrapStyle = useMemo(
    () => [styles.contentWrap, { paddingBottom: insets.bottom + 10 }],
    [insets.bottom],
  );
  const tabbedJobsListWrapStyle = useMemo(
    () => [styles.jobsListWrap, { paddingBottom: insets.bottom + 10 }],
    [insets.bottom],
  );
  const tabbedNativeContentWrapStyle = useMemo(
    () => [styles.nativeContentWrap, { paddingBottom: insets.bottom + 10 }],
    [insets.bottom],
  );

  const renderNativeBottomTabs = useCallback(() => {
    const tabNames: Array<keyof RootTabParamList> = [
      'Estimates',
      'Shopping',
      'Planner',
      'Expenses',
      'Staff',
    ];
    return (
      <View style={nativeTabHostStyle}>
        <NavigationContainer ref={tabNavigationRef}>
          <Tab.Navigator
            initialRouteName={TAB_NAME_BY_MAIN[mainTab]}
            screenOptions={({ route }) => ({
              headerShown: false,
              lazy: true,
              tabBarShowLabel: true,
              tabBarLabelPosition: 'below-icon',
              tabBarStyle: nativeTabBarStyle,
              tabBarItemStyle: styles.nativeTabItem,
              tabBarIconStyle: styles.nativeTabIcon,
              tabBarLabelStyle: styles.nativeTabLabel,
              tabBarActiveTintColor: '#0f766e',
              tabBarInactiveTintColor: '#8E8E93',
              tabBarActiveBackgroundColor: 'transparent',
              tabBarInactiveBackgroundColor: 'transparent',
              tabBarHideOnKeyboard: true,
              tabBarButton: (props) => (
                <TouchableOpacity
                  {...props}
                  activeOpacity={0.75}
                  delayPressIn={0}
                  hitSlop={{ top: 8, bottom: 8, left: 6, right: 6 }}
                  style={[props.style, styles.nativeTabButton]}
                />
              ),
              tabBarIcon: ({ color }) =>
                renderMainTabIcon(route.name as keyof RootTabParamList, color, 22),
            })}
          >
            {tabNames.map((tabName) => (
              <Tab.Screen
                key={tabName}
                name={tabName}
                component={EmptyTabScreen}
                listeners={{
                  tabPress: (event) => {
                    const nextTab = MAIN_TAB_BY_NAME[tabName];
                    if (
                      nextTab === 'staff' &&
                      selectedEstimate &&
                      !selectedEstimate.can_manage_staff
                    ) {
                      event.preventDefault();
                      Alert.alert('No access', 'Your account cannot manage staff on this estimate.');
                      return;
                    }
                    switchMainTab(nextTab);
                  },
                }}
              />
            ))}
          </Tab.Navigator>
        </NavigationContainer>
      </View>
    );
  }, [mainTab, nativeTabBarStyle, nativeTabHostStyle, selectedEstimate, switchMainTab]);

  const handleBackChevron = useCallback(() => {
    if (plannerEditorVisible) {
      setPlannerEditorVisible(false);
      setPlannerEditingEntryId(null);
      setPlannerEditorGroupCode('');
      setPlannerEditorItemCode('');
      setPlannerEditorValues({});
      setPlannerEditorFieldDraftValues({});
      setPlannerEditorNotes('');
      setPlannerEditorChecked(false);
      setPlannerEditorFieldCards([]);
      setPlannerFieldCardsManagerOpen(false);
      setPlannerNewOptionName('');
      return;
    }
    if (mainTab === 'shopping') {
      if (shoppingItemEditorOpen) {
        setShoppingItemEditorOpen(false);
        setShoppingEditingItemId(null);
        setShoppingEditName('');
        setShoppingEditType('');
        setShoppingEditQty('');
        setShoppingEditUnit('');
        setSavingShoppingEdit(false);
        return;
      }
      if (selectedShoppingList) {
        setSelectedShoppingList(null);
        setShoppingItems([]);
        setSavedItemSearchText('');
        setSavedItemExpandedKey(null);
        setSavedItemQuickQty('1');
        setSavedItemQuickUnit('');
        setSavedItemQuickType('');
        setSavedItemQuickUnitPickerOpen(false);
        setShoppingListScreenMode('manage');
        return;
      }
      return;
    }
    if (mainTab === 'planner') {
      if (plannerCategoryCode) {
        setPlannerCategoryCode('');
        setPlannerSearchText('');
        return;
      }
      if (plannerSection) {
        setPlannerSection(null);
        return;
      }
      if (selectedPlannerEstimate) {
        setSelectedPlannerEstimate(null);
        setPlannerSection(null);
        setPlannerCategoryCode('');
        setPlannerSearchText('');
      }
      return;
    }
    if ((mainTab === 'expenses' || mainTab === 'staff') && selectedEstimate) {
      setSelectedEstimate(null);
    }
  }, [
    mainTab,
    plannerCategoryCode,
    plannerEditorVisible,
    plannerSection,
    shoppingItemEditorOpen,
    selectedEstimate,
    selectedPlannerEstimate,
    selectedShoppingList,
  ]);

  const showBackChevron = useMemo(() => {
    if (plannerEditorVisible) return true;
    if (mainTab === 'shopping') {
      return shoppingItemEditorOpen || !!selectedShoppingList;
    }
    if (mainTab === 'planner') {
      return !!selectedPlannerEstimate || !!plannerSection || !!plannerCategoryCode;
    }
    if (mainTab === 'expenses' || mainTab === 'staff') {
      return !!selectedEstimate;
    }
    return false;
  }, [
    mainTab,
    plannerCategoryCode,
    plannerEditorVisible,
    plannerSection,
    shoppingItemEditorOpen,
    selectedEstimate,
    selectedPlannerEstimate,
    selectedShoppingList,
  ]);

  const openAdminPath = useCallback(
    (path: string) => {
      Linking.openURL(apiUrl(apiBaseUrl, path)).catch(() => {
        Alert.alert('Open failed', 'Unable to open admin page on this device.');
      });
    },
    [apiBaseUrl],
  );

  const buildEstimatePrintPdf = useCallback(
    async (estimate: EstimateRow, variant: EstimatePrintVariant) => {
      if (!token) {
        throw new Error('Authentication required.');
      }
      const response = await fetch(
        apiUrl(apiBaseUrl, `/api/xpenz/estimates/${estimate.id}/print-html/?variant=${variant}`),
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      if (!response.ok) {
        let errorMessage = 'Unable to load print preview.';
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const payload = await response.json().catch(() => ({}));
          errorMessage = payload?.error || errorMessage;
        } else {
          const rawBody = await response.text().catch(() => '');
          if (rawBody.includes('/admin/login') || rawBody.toLowerCase().includes('login')) {
            errorMessage = 'Server returned a login page for this print preview. Try again after backend deploy.';
          } else if (response.status >= 500) {
            errorMessage = `Print preview failed on the server (${response.status}).`;
          } else if (response.status === 404) {
            errorMessage = 'Print endpoint not found on server. Deploy backend updates and retry.';
          } else if (response.status >= 400) {
            errorMessage = `Print preview request failed (${response.status}).`;
          }
        }
        throw new Error(errorMessage);
      }

      const html = await response.text();
      const baseHref = `${normalizeBaseUrl(apiBaseUrl)}/`;
      const htmlWithBase = /<base\s/i.test(html)
        ? html
        : html.replace(/<head(\s[^>]*)?>/i, (match) => `${match}<base href="${baseHref}">`);
      const htmlForPdf = htmlWithBase.replace(/@media\s+print/gi, '@media all');
      const file = await Print.printToFileAsync({
        html: htmlForPdf,
        width: PDF_A4_WIDTH_POINTS,
        height: PDF_A4_HEIGHT_POINTS,
        margins: {
          top: 0,
          right: 0,
          bottom: 0,
          left: 0,
        },
      });
      return { uri: file.uri, html: htmlForPdf };
    },
    [apiBaseUrl, token],
  );

  const openEstimatePrintOptions = useCallback(
    (estimate: EstimateRow) => {
      if (generatingPrintPdf) {
        Alert.alert('Please wait', 'A PDF is currently being prepared.');
        return;
      }
      const runPrintFlow = async (variant: EstimatePrintVariant, title: string) => {
        try {
          setGeneratingPrintPdf(true);
          const pdf = await buildEstimatePrintPdf(estimate, variant);
          setGeneratingPrintPdf(false);
          Alert.alert(`${title} ready`, 'Preview, share, or print this PDF.', [
            { text: 'Close', style: 'cancel' },
            {
              text: 'Preview',
              onPress: () => {
                Linking.openURL(pdf.uri).catch(() => {
                  Alert.alert('Open failed', 'Unable to open the PDF preview.');
                });
              },
            },
            {
              text: 'Share',
              onPress: async () => {
                try {
                  const isSharingAvailable = await Sharing.isAvailableAsync();
                  if (!isSharingAvailable) {
                    throw new Error('Sharing is not available on this device.');
                  }
                  await Sharing.shareAsync(pdf.uri, {
                    dialogTitle: title,
                  });
                } catch (error) {
                  Alert.alert(
                    'Share failed',
                    error instanceof Error ? error.message : 'Unable to share this PDF.',
                  );
                }
              },
            },
            {
              text: 'Print',
              onPress: async () => {
                try {
                  await Print.printAsync({ html: pdf.html });
                } catch {
                  Alert.alert('Print failed', 'Unable to open the print dialog.');
                }
              },
            },
          ]);
        } catch (error) {
          Alert.alert(
            'Print failed',
            error instanceof Error ? error.message : 'Unable to prepare this print view.',
          );
        } finally {
          setGeneratingPrintPdf(false);
        }
      };

      Alert.alert('Print & Share', estimate.job_name, [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Estimate PDF',
          onPress: () => {
            runPrintFlow('estimate', 'Estimate PDF');
          },
        },
        {
          text: 'Flat PDF',
          onPress: () => {
            runPrintFlow('flat', 'Flat PDF');
          },
        },
        {
          text: 'Planner Print',
          onPress: () => {
            runPrintFlow('planner', 'Planner Print');
          },
        },
        {
          text: 'Kitchen Workflow',
          onPress: () => {
            runPrintFlow('workflow', 'Kitchen Workflow');
          },
        },
      ]);
    },
    [buildEstimatePrintPdf, generatingPrintPdf],
  );

  const submitEstimateFromMobile = useCallback(async () => {
    if (!token) {
      return;
    }
    if (!newEstimateCustomer.trim()) {
      Alert.alert('Missing customer', 'Enter the customer name.');
      return;
    }
    setCreatingEstimate(true);
    try {
      const response = await fetch(apiUrl(apiBaseUrl, '/api/xpenz/estimates/'), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          customer_name: newEstimateCustomer.trim(),
          event_type: newEstimateEventType.trim() || 'Event',
          event_date: newEstimateDate.trim() || undefined,
          event_location: newEstimateLocation.trim(),
          guest_count: newEstimateAdults.trim() || '0',
          guest_count_kids: newEstimateKids.trim() || '0',
          caterer_id: newEstimateCatererId || undefined,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false || !payload.estimate) {
        throw new Error(payload.error || 'Unable to create estimate.');
      }
      setEstimateComposerOpen(false);
      setNewEstimateCustomer('');
      setNewEstimateEventType('Event');
      setNewEstimateDate('');
      setNewEstimateLocation('');
      setNewEstimateAdults('');
      setNewEstimateKids('');
      await loadEstimates();
      Alert.alert('Estimate created', 'Your new estimate is now in the list.');
    } catch (error) {
      Alert.alert(
        'Create estimate failed',
        error instanceof Error ? error.message : 'Unable to create estimate.',
      );
    } finally {
      setCreatingEstimate(false);
    }
  }, [
    apiBaseUrl,
    loadEstimates,
    newEstimateAdults,
    newEstimateCatererId,
    newEstimateCustomer,
    newEstimateDate,
    newEstimateEventType,
    newEstimateKids,
    newEstimateLocation,
    token,
  ]);

  const applyEstimateBuilderPayload = useCallback((payload: Record<string, unknown>) => {
    const estimate = (payload.estimate || null) as EstimateBuilderEstimate | null;
    const catalog = (payload.catalog || null) as EstimateBuilderCatalog | null;
    const selections = (payload.selections || {}) as {
      menu_choices?: unknown;
      extra_lines?: unknown;
    };
    if (!estimate || !catalog) {
      throw new Error('Builder payload is incomplete.');
    }
    const menuChoices = Array.isArray(selections.menu_choices)
      ? (selections.menu_choices as EstimateBuilderMenuChoice[])
      : [];
    const extraLines = Array.isArray(selections.extra_lines)
      ? (selections.extra_lines as EstimateBuilderExtraLine[])
      : [];
    const estimateMeals = Array.isArray(estimate.meal_plan) ? estimate.meal_plan : [];
    const catalogMeals = Array.isArray(catalog.meal_plan) ? catalog.meal_plan : [];
    let mealPlanValues = mergeOptionValues(estimateMeals.length ? estimateMeals : catalogMeals);
    if (mealPlanValues.length > 1) {
      mealPlanValues = mealPlanValues.filter((name) => name.trim().toLowerCase() !== 'signature menu');
    }
    if (!mealPlanValues.length) {
      mealPlanValues = ['Signature Menu'];
    }
    const rawManualMealTotals =
      estimate.manual_meal_totals && typeof estimate.manual_meal_totals === 'object'
        ? (estimate.manual_meal_totals as Record<string, unknown>)
        : {};
    const normalizedManualMealTotals: Record<string, string> = {};
    const manualMealTotalsByKey = new Map<string, string>();
    for (const [rawMealName, rawValue] of Object.entries(rawManualMealTotals)) {
      const mealName = (rawMealName || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealName || !mealKey) {
        continue;
      }
      const value = String(rawValue ?? '').trim();
      if (!value) {
        continue;
      }
      normalizedManualMealTotals[mealName] = value;
      manualMealTotalsByKey.set(mealKey, value);
    }

    const rawMealGuestOverrides =
      estimate.meal_guest_overrides && typeof estimate.meal_guest_overrides === 'object'
        ? (estimate.meal_guest_overrides as Record<string, unknown>)
        : {};
    const normalizedMealGuestOverrides: Record<string, EstimateBuilderMealGuestOverride> = {};
    const mealGuestOverridesByKey = new Map<string, EstimateBuilderMealGuestOverride>();
    for (const [rawMealName, rawValue] of Object.entries(rawMealGuestOverrides)) {
      const mealName = (rawMealName || '').trim();
      if (!mealName || !rawValue || typeof rawValue !== 'object') {
        continue;
      }
      const row = rawValue as Record<string, unknown>;
      const adults = Number.parseInt(String(row.adults ?? '').trim(), 10);
      const kids = Number.parseInt(String(row.kids ?? '').trim(), 10);
      const normalizedRow: EstimateBuilderMealGuestOverride = {};
      if (Number.isFinite(adults) && adults >= 0) {
        normalizedRow.adults = adults;
      }
      if (Number.isFinite(kids) && kids >= 0) {
        normalizedRow.kids = kids;
      }
      if (normalizedRow.adults != null || normalizedRow.kids != null) {
        normalizedMealGuestOverrides[mealName] = normalizedRow;
        mealGuestOverridesByKey.set(normalizeEstimateMealKey(mealName), normalizedRow);
      }
    }

    const mealSections = Array.isArray(estimate.meal_sections)
      ? estimate.meal_sections.filter(
          (row) =>
            !!row &&
            typeof row === 'object' &&
            typeof (row as EstimateBuilderMealSection).name === 'string',
        )
      : [];

    const normalizedEstimate: EstimateBuilderEstimate = {
      ...estimate,
      manual_meal_totals: normalizedManualMealTotals,
      meal_guest_overrides: normalizedMealGuestOverrides,
      meal_sections: mealSections,
    };

    const mealOverrideDrafts: Record<string, EstimateBuilderMealOverrideDraft> = {};
    const draftMealNames = mergeOptionValues(
      mealPlanValues,
      Object.keys(normalizedManualMealTotals),
      Object.keys(normalizedMealGuestOverrides),
    );
    for (const mealName of draftMealNames) {
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealKey) {
        continue;
      }
      const overridePrice = String(manualMealTotalsByKey.get(mealKey) ?? '').trim();
      const guestOverride = mealGuestOverridesByKey.get(mealKey) || {};
      mealOverrideDrafts[mealKey] = {
        override_price: overridePrice,
        adults:
          guestOverride.adults == null || Number.isNaN(guestOverride.adults)
            ? ''
            : String(guestOverride.adults),
        kids:
          guestOverride.kids == null || Number.isNaN(guestOverride.kids)
            ? ''
            : String(guestOverride.kids),
      };
    }

    setEstimateBuilderEstimate(normalizedEstimate);
    setEstimateBuilderCatalog(catalog);
    setEstimateBuilderMenuChoices(menuChoices);
    setEstimateBuilderExtraLines(extraLines);
    setEstimateBuilderMealOverrideDrafts(mealOverrideDrafts);
    setEstimateBuilderMealPlanInput(mealPlanValues.join('\n'));
    setEstimateBuilderActiveMeal((previous) =>
      previous && mealPlanValues.some((name) => name.toLowerCase() === previous.toLowerCase())
        ? previous
        : mealPlanValues[0] || 'Signature Menu',
    );
  }, []);

  const openEstimateBuilder = useCallback(
    async (estimate: EstimateRow) => {
      if (!token) {
        return;
      }
      setEstimateBuilderOpen(true);
      setEstimateBuilderLoading(true);
      setEstimateBuilderSaving(false);
      setEstimateBuilderStep('customer');
      setEstimateBuilderMenuSearch('');
      setEstimateBuilderExtrasSearch('');
      setEstimateBuilderMealOverrideDrafts({});
      try {
        const payload = await authFetchJson(
          `/api/xpenz/estimates/${estimate.id}/builder/`,
          { method: 'GET' },
        );
        applyEstimateBuilderPayload(payload as Record<string, unknown>);
      } catch (error) {
        setEstimateBuilderOpen(false);
        Alert.alert(
          'Builder load failed',
          error instanceof Error ? error.message : 'Unable to load estimate builder.',
        );
      } finally {
        setEstimateBuilderLoading(false);
      }
    },
    [applyEstimateBuilderPayload, authFetchJson, token],
  );

  const closeEstimateBuilder = useCallback(() => {
    setEstimateBuilderOpen(false);
    setEstimateBuilderLoading(false);
    setEstimateBuilderSaving(false);
    setEstimateBuilderStep('customer');
    setEstimateBuilderEstimate(null);
    setEstimateBuilderCatalog(null);
    setEstimateBuilderMenuChoices([]);
    setEstimateBuilderExtraLines([]);
    setEstimateBuilderMealPlanInput('');
    setEstimateBuilderActiveMeal('');
    setEstimateBuilderMealOverrideDrafts({});
    setEstimateBuilderMenuSearch('');
    setEstimateBuilderExtrasSearch('');
  }, []);

  const buildEstimateBuilderMealOverridesPayload = useCallback(() => {
    if (!estimateBuilderEstimate) {
      return {
        ok: false as const,
        error: 'Estimate data is not loaded.',
      };
    }
    const manualMealTotals: Record<string, string> = {};
    const mealGuestOverrides: Record<string, EstimateBuilderMealGuestOverride> = {};
    const planMeals = estimateBuilderMealPlan.length ? estimateBuilderMealPlan : ['Signature Menu'];

    const manualByKey = new Map<string, string>();
    for (const [rawMealName, rawValue] of Object.entries(
      estimateBuilderEstimate.manual_meal_totals || {},
    )) {
      const mealName = (rawMealName || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealName || !mealKey) {
        continue;
      }
      const parsedValue = parseNonNegativeDecimalInput(String(rawValue ?? ''));
      if (Number.isNaN(parsedValue)) {
        return {
          ok: false as const,
          error: `Price override for "${mealName}" must be a non-negative number.`,
        };
      }
      if (parsedValue == null) {
        continue;
      }
      manualByKey.set(mealKey, parsedValue.toFixed(2));
    }

    const guestByKey = new Map<string, EstimateBuilderMealGuestOverride>();
    for (const [rawMealName, rawRow] of Object.entries(
      estimateBuilderEstimate.meal_guest_overrides || {},
    )) {
      const mealName = (rawMealName || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealName || !mealKey || !rawRow || typeof rawRow !== 'object') {
        continue;
      }
      const row = rawRow as EstimateBuilderMealGuestOverride;
      const parsedAdults = parseNonNegativeIntegerInput(String(row.adults ?? ''));
      if (Number.isNaN(parsedAdults)) {
        return {
          ok: false as const,
          error: `Adults override for "${mealName}" must be a non-negative whole number.`,
        };
      }
      const parsedKids = parseNonNegativeIntegerInput(String(row.kids ?? ''));
      if (Number.isNaN(parsedKids)) {
        return {
          ok: false as const,
          error: `Kids override for "${mealName}" must be a non-negative whole number.`,
        };
      }
      if (parsedAdults == null && parsedKids == null) {
        continue;
      }
      guestByKey.set(mealKey, {
        ...(parsedAdults != null ? { adults: parsedAdults } : {}),
        ...(parsedKids != null ? { kids: parsedKids } : {}),
      });
    }

    const consumedKeys = new Set<string>();
    for (const mealName of planMeals) {
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealKey || consumedKeys.has(mealKey)) {
        continue;
      }
      consumedKeys.add(mealKey);
      const priceOverride = manualByKey.get(mealKey);
      if (priceOverride != null) {
        manualMealTotals[mealName] = priceOverride;
      }
      const guestOverride = guestByKey.get(mealKey);
      if (guestOverride) {
        mealGuestOverrides[mealName] = {};
        if (guestOverride.adults != null) {
          mealGuestOverrides[mealName].adults = guestOverride.adults;
        }
        if (guestOverride.kids != null) {
          mealGuestOverrides[mealName].kids = guestOverride.kids;
        }
      }
    }

    return {
      ok: true as const,
      manualMealTotals,
      mealGuestOverrides,
    };
  }, [estimateBuilderEstimate, estimateBuilderMealPlan]);

  const saveEstimateBuilder = useCallback(async () => {
    if (!estimateBuilderEstimate || !token) {
      return;
    }
    if (!estimateBuilderEstimate.can_edit) {
      Alert.alert('No access', 'Your account cannot edit this estimate.');
      return;
    }
    if (!estimateBuilderEstimate.customer_name.trim()) {
      Alert.alert('Missing customer', 'Enter a customer name before saving.');
      return;
    }
    const mealOverridePayload = buildEstimateBuilderMealOverridesPayload();
    if (!mealOverridePayload.ok) {
      Alert.alert('Invalid meal override', mealOverridePayload.error);
      return;
    }
    setEstimateBuilderSaving(true);
    try {
      const payload = await authFetchJson(
        `/api/xpenz/estimates/${estimateBuilderEstimate.id}/builder/`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            estimate: {
              customer_name: estimateBuilderEstimate.customer_name,
              customer_phone: estimateBuilderEstimate.customer_phone,
              customer_email: estimateBuilderEstimate.customer_email,
              event_type: estimateBuilderEstimate.event_type,
              event_date: estimateBuilderEstimate.event_date,
              event_location: estimateBuilderEstimate.event_location,
              guest_count: estimateBuilderEstimate.guest_count,
              guest_count_kids: estimateBuilderEstimate.guest_count_kids,
              currency: estimateBuilderEstimate.currency,
              is_ala_carte: estimateBuilderEstimate.is_ala_carte,
              include_premium_plastic: estimateBuilderEstimate.include_premium_plastic,
              include_premium_tablecloths: estimateBuilderEstimate.include_premium_tablecloths,
              plasticware_color: estimateBuilderEstimate.plasticware_color,
              wants_real_dishes: estimateBuilderEstimate.wants_real_dishes,
              real_dishes_price_per_person: estimateBuilderEstimate.real_dishes_price_per_person,
              real_dishes_flat_fee: estimateBuilderEstimate.real_dishes_flat_fee,
              staff_hours: estimateBuilderEstimate.staff_hours,
              extra_waiters: estimateBuilderEstimate.extra_waiters,
              staff_count_override: estimateBuilderEstimate.staff_count_override,
              staff_hourly_rate: estimateBuilderEstimate.staff_hourly_rate,
              staff_tip_per_waiter: estimateBuilderEstimate.staff_tip_per_waiter,
              client_tipped_at_event: estimateBuilderEstimate.client_tipped_at_event,
              deposit_percentage: estimateBuilderEstimate.deposit_percentage,
              deposit_received: estimateBuilderEstimate.deposit_received,
              kids_discount_percentage: estimateBuilderEstimate.kids_discount_percentage,
              exchange_rate: estimateBuilderEstimate.exchange_rate,
              notes_internal: estimateBuilderEstimate.notes_internal,
              notes_for_customer: estimateBuilderEstimate.notes_for_customer,
              payment_terms: estimateBuilderEstimate.payment_terms,
              payment_method: estimateBuilderEstimate.payment_method,
              payment_instructions: estimateBuilderEstimate.payment_instructions,
              contract_terms: estimateBuilderEstimate.contract_terms,
              terms_acknowledged: estimateBuilderEstimate.terms_acknowledged,
              signature_name: estimateBuilderEstimate.signature_name,
              signature_title: estimateBuilderEstimate.signature_title,
              signature_date: estimateBuilderEstimate.signature_date,
              manual_meal_totals: mealOverridePayload.manualMealTotals,
              meal_guest_overrides: mealOverridePayload.mealGuestOverrides,
              tablecloth_details: estimateBuilderEstimate.tablecloth_details,
            },
            meal_plan: estimateBuilderMealPlan,
            menu_choices: estimateBuilderMenuChoices,
            extra_lines: estimateBuilderExtraLines,
          }),
        },
      );
      applyEstimateBuilderPayload(payload as Record<string, unknown>);
      await loadEstimates();
      Alert.alert('Saved', 'Estimate builder changes were saved.');
    } catch (error) {
      Alert.alert(
        'Save failed',
        error instanceof Error ? error.message : 'Unable to save estimate builder changes.',
      );
    } finally {
      setEstimateBuilderSaving(false);
    }
  }, [
    applyEstimateBuilderPayload,
    authFetchJson,
    buildEstimateBuilderMealOverridesPayload,
    estimateBuilderEstimate,
    estimateBuilderExtraLines,
    estimateBuilderMealPlan,
    estimateBuilderMenuChoices,
    loadEstimates,
    token,
  ]);

  const activeEstimateBuilderMeal = useMemo(
    () => estimateBuilderActiveMeal || estimateBuilderMealPlan[0] || 'Signature Menu',
    [estimateBuilderActiveMeal, estimateBuilderMealPlan],
  );

  const estimateBuilderMealSectionMap = useMemo(() => {
    const map = new Map<string, EstimateBuilderMealSection>();
    const sections = estimateBuilderEstimate?.meal_sections || [];
    for (const section of sections) {
      const mealName = (section?.name || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealName || !mealKey || map.has(mealKey)) {
        continue;
      }
      map.set(mealKey, section);
    }
    return map;
  }, [estimateBuilderEstimate?.meal_sections]);

  const estimateBuilderManualMealTotalsByKey = useMemo(() => {
    const map = new Map<string, string>();
    const rows = estimateBuilderEstimate?.manual_meal_totals || {};
    for (const [rawMealName, rawValue] of Object.entries(rows)) {
      const mealName = (rawMealName || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      const value = String(rawValue ?? '').trim();
      if (!mealName || !mealKey || !value) {
        continue;
      }
      map.set(mealKey, value);
    }
    return map;
  }, [estimateBuilderEstimate?.manual_meal_totals]);

  const estimateBuilderMealGuestOverridesByKey = useMemo(() => {
    const map = new Map<string, EstimateBuilderMealGuestOverride>();
    const rows = estimateBuilderEstimate?.meal_guest_overrides || {};
    for (const [rawMealName, rawValue] of Object.entries(rows)) {
      const mealName = (rawMealName || '').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealName || !mealKey || !rawValue || typeof rawValue !== 'object') {
        continue;
      }
      const row = rawValue as EstimateBuilderMealGuestOverride;
      const normalizedRow: EstimateBuilderMealGuestOverride = {};
      if (row.adults != null && Number.isFinite(Number(row.adults)) && Number(row.adults) >= 0) {
        normalizedRow.adults = Number(row.adults);
      }
      if (row.kids != null && Number.isFinite(Number(row.kids)) && Number(row.kids) >= 0) {
        normalizedRow.kids = Number(row.kids);
      }
      if (normalizedRow.adults != null || normalizedRow.kids != null) {
        map.set(mealKey, normalizedRow);
      }
    }
    return map;
  }, [estimateBuilderEstimate?.meal_guest_overrides]);

  const activeEstimateBuilderMealKey = useMemo(
    () => normalizeEstimateMealKey(activeEstimateBuilderMeal),
    [activeEstimateBuilderMeal],
  );

  const activeEstimateBuilderMealSection = useMemo(
    () => estimateBuilderMealSectionMap.get(activeEstimateBuilderMealKey) || null,
    [activeEstimateBuilderMealKey, estimateBuilderMealSectionMap],
  );

  const activeEstimateBuilderCommittedPriceOverride = useMemo(
    () => estimateBuilderManualMealTotalsByKey.get(activeEstimateBuilderMealKey) || '',
    [activeEstimateBuilderMealKey, estimateBuilderManualMealTotalsByKey],
  );

  const activeEstimateBuilderCommittedGuestOverride = useMemo(
    () => estimateBuilderMealGuestOverridesByKey.get(activeEstimateBuilderMealKey) || {},
    [activeEstimateBuilderMealKey, estimateBuilderMealGuestOverridesByKey],
  );

  const activeEstimateBuilderMealDraft = useMemo(
    () => {
      const draft = estimateBuilderMealOverrideDrafts[activeEstimateBuilderMealKey];
      if (draft) {
        return draft;
      }
      return {
        override_price: activeEstimateBuilderCommittedPriceOverride,
        adults:
          activeEstimateBuilderCommittedGuestOverride.adults == null
            ? ''
            : String(activeEstimateBuilderCommittedGuestOverride.adults),
        kids:
          activeEstimateBuilderCommittedGuestOverride.kids == null
            ? ''
            : String(activeEstimateBuilderCommittedGuestOverride.kids),
      };
    },
    [
      activeEstimateBuilderCommittedGuestOverride.adults,
      activeEstimateBuilderCommittedGuestOverride.kids,
      activeEstimateBuilderCommittedPriceOverride,
      activeEstimateBuilderMealKey,
      estimateBuilderMealOverrideDrafts,
    ],
  );

  const activeEstimateBuilderMealDefaultAdults = useMemo(() => {
    const sectionValue = Number.parseInt(
      String(activeEstimateBuilderMealSection?.guest_count ?? '').trim(),
      10,
    );
    if (Number.isFinite(sectionValue) && sectionValue >= 0) {
      return sectionValue;
    }
    return estimateBuilderEstimate?.guest_count || 0;
  }, [activeEstimateBuilderMealSection?.guest_count, estimateBuilderEstimate?.guest_count]);

  const activeEstimateBuilderMealDefaultKids = useMemo(() => {
    const sectionValue = Number.parseInt(
      String(activeEstimateBuilderMealSection?.guest_count_kids ?? '').trim(),
      10,
    );
    if (Number.isFinite(sectionValue) && sectionValue >= 0) {
      return sectionValue;
    }
    return estimateBuilderEstimate?.guest_count_kids || 0;
  }, [activeEstimateBuilderMealSection?.guest_count_kids, estimateBuilderEstimate?.guest_count_kids]);

  const activeEstimateBuilderMealEffectiveAdults = useMemo(() => {
    const parsed = parseNonNegativeIntegerInput(
      String(activeEstimateBuilderCommittedGuestOverride.adults ?? ''),
    );
    if (Number.isNaN(parsed)) {
      return activeEstimateBuilderMealDefaultAdults;
    }
    return parsed == null ? activeEstimateBuilderMealDefaultAdults : parsed;
  }, [activeEstimateBuilderCommittedGuestOverride.adults, activeEstimateBuilderMealDefaultAdults]);

  const activeEstimateBuilderMealEffectiveKids = useMemo(() => {
    const parsed = parseNonNegativeIntegerInput(
      String(activeEstimateBuilderCommittedGuestOverride.kids ?? ''),
    );
    if (Number.isNaN(parsed)) {
      return activeEstimateBuilderMealDefaultKids;
    }
    return parsed == null ? activeEstimateBuilderMealDefaultKids : parsed;
  }, [activeEstimateBuilderCommittedGuestOverride.kids, activeEstimateBuilderMealDefaultKids]);

  const estimateBuilderMenuItemPricingById = useMemo(() => {
    const map = new Map<
      number,
      {
        pricePerServing: number;
        defaultServingsPerPerson: number;
        isKidsCategory: boolean;
      }
    >();
    const categories = estimateBuilderCatalog?.menu_categories || [];
    for (const category of categories) {
      const categoryName = String(category?.name || '').toLowerCase();
      const isKidsCategory = categoryName.includes('kid') || categoryName.includes('child');
      for (const item of category.items || []) {
        const parsedPrice = parseNonNegativeDecimalInput(String(item.price_per_serving ?? ''));
        const parsedDefaultServings = parseNonNegativeDecimalInput(
          String(item.default_servings_per_person ?? ''),
        );
        map.set(Number(item.id), {
          pricePerServing: Number.isFinite(parsedPrice as number) ? Number(parsedPrice) : 0,
          defaultServingsPerPerson: Number.isFinite(parsedDefaultServings as number)
            ? Number(parsedDefaultServings)
            : 1,
          isKidsCategory,
        });
      }
    }
    return map;
  }, [estimateBuilderCatalog?.menu_categories]);

  const estimateBuilderMealPriceFromSelectionsByKey = useMemo(() => {
    const totals = new Map<string, number>();
    const map = new Map<string, string>();
    const exchangeRateParsed = parseNonNegativeDecimalInput(
      String(estimateBuilderEstimate?.exchange_rate ?? '1'),
    );
    const exchangeRate =
      Number.isFinite(exchangeRateParsed as number) && Number(exchangeRateParsed) > 0
        ? Number(exchangeRateParsed)
        : 1;
    const defaultMealName = estimateBuilderMealPlan[0] || activeEstimateBuilderMeal || 'Signature Menu';

    for (const choice of estimateBuilderMenuChoices) {
      if (!choice?.included) {
        continue;
      }
      const mealName = (choice.meal_name || defaultMealName || 'Signature Menu').trim();
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealKey) {
        continue;
      }
      const itemPricing = estimateBuilderMenuItemPricingById.get(Number(choice.menu_item_id));
      if (!itemPricing || itemPricing.isKidsCategory) {
        continue;
      }
      const servingsParsed = parseNonNegativeDecimalInput(String(choice.servings_per_person ?? ''));
      if (Number.isNaN(servingsParsed)) {
        continue;
      }
      const servings =
        Number.isFinite(servingsParsed as number) && Number(servingsParsed) >= 0
          ? Number(servingsParsed)
          : itemPricing.defaultServingsPerPerson;
      const lineTotal = servings * itemPricing.pricePerServing * exchangeRate;
      if (!Number.isFinite(lineTotal)) {
        continue;
      }
      totals.set(mealKey, (totals.get(mealKey) || 0) + lineTotal);
    }

    for (const [mealKey, total] of totals.entries()) {
      map.set(mealKey, total.toFixed(2));
    }
    return map;
  }, [
    activeEstimateBuilderMeal,
    estimateBuilderEstimate?.exchange_rate,
    estimateBuilderMealPlan,
    estimateBuilderMenuChoices,
    estimateBuilderMenuItemPricingById,
  ]);

  const estimateBuilderHeaderMealPriceCards = useMemo(() => {
    const mealSections = estimateBuilderEstimate?.meal_sections || [];
    const candidateMeals = mergeOptionValues(
      estimateBuilderMealPlan,
      mealSections.map((section) => section.name),
      Object.keys(estimateBuilderEstimate?.manual_meal_totals || {}),
    );
    const orderedMeals = candidateMeals.length
      ? candidateMeals
      : [activeEstimateBuilderMeal || 'Signature Menu'];
    const isMultiMeal = orderedMeals.length > 1;
    return orderedMeals.map((mealName, mealIndex) => {
      const mealKey = normalizeEstimateMealKey(mealName);
      const mealSection =
        estimateBuilderMealSectionMap.get(mealKey) ||
        (mealSections.length === orderedMeals.length ? mealSections[mealIndex] : undefined);
      const overrideValue = parseNonNegativeDecimalInput(
        estimateBuilderManualMealTotalsByKey.get(mealKey) || '',
      );
      let pricePerGuest = '';
      if (Number.isFinite(overrideValue as number)) {
        pricePerGuest = (overrideValue as number).toFixed(2);
      } else {
        const selectionComputedPrice = parseNonNegativeDecimalInput(
          estimateBuilderMealPriceFromSelectionsByKey.get(mealKey) || '',
        );
        if (Number.isFinite(selectionComputedPrice as number)) {
          pricePerGuest = (selectionComputedPrice as number).toFixed(2);
        } else {
          const sectionPrice = parseNonNegativeDecimalInput(String(mealSection?.price_per_guest || ''));
          if (Number.isFinite(sectionPrice as number)) {
            pricePerGuest = (sectionPrice as number).toFixed(2);
          } else {
            const sectionTotal = parseNonNegativeDecimalInput(String(mealSection?.total || ''));
            const sectionAdults = parseNonNegativeIntegerInput(String(mealSection?.guest_count || ''));
            if (
              Number.isFinite(sectionTotal as number) &&
              Number.isFinite(sectionAdults as number) &&
              Number(sectionAdults) > 0
            ) {
              pricePerGuest = (Number(sectionTotal) / Number(sectionAdults)).toFixed(2);
            }
          }
        }
      }
      if (!pricePerGuest) {
        pricePerGuest = isMultiMeal
          ? ''
          : (estimateBuilderEstimate?.summary.food_price_per_person || '').trim();
      }
      return {
        mealName,
        pricePerGuest,
      };
    });
  }, [
    activeEstimateBuilderMeal,
    estimateBuilderEstimate?.manual_meal_totals,
    estimateBuilderEstimate?.meal_sections,
    estimateBuilderEstimate?.summary.food_price_per_person,
    estimateBuilderManualMealTotalsByKey,
    estimateBuilderMealPriceFromSelectionsByKey,
    estimateBuilderMealPlan,
    estimateBuilderMealSectionMap,
  ]);

  const estimateBuilderHasMultiMealPrices = estimateBuilderHeaderMealPriceCards.length > 1;

  const estimateBuilderResolvedMealPriceByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of estimateBuilderHeaderMealPriceCards) {
      const mealKey = normalizeEstimateMealKey(row.mealName);
      if (!mealKey) {
        continue;
      }
      map.set(mealKey, row.pricePerGuest);
    }
    return map;
  }, [estimateBuilderHeaderMealPriceCards]);

  const activeEstimateBuilderMealEffectivePricePerGuest = useMemo(
    () => estimateBuilderResolvedMealPriceByKey.get(activeEstimateBuilderMealKey) || '',
    [activeEstimateBuilderMealKey, estimateBuilderResolvedMealPriceByKey],
  );

  const estimateBuilderHeaderMealPriceCardRows = useMemo(() => {
    const rows: Array<Array<{ mealName: string; pricePerGuest: string }>> = [];
    for (let index = 0; index < estimateBuilderHeaderMealPriceCards.length; index += 2) {
      rows.push(estimateBuilderHeaderMealPriceCards.slice(index, index + 2));
    }
    return rows;
  }, [estimateBuilderHeaderMealPriceCards]);

  const updateEstimateBuilderMealOverrideDraft = useCallback(
    (
      mealName: string,
      field: keyof EstimateBuilderMealOverrideDraft,
      value: string,
    ) => {
      const mealKey = normalizeEstimateMealKey(mealName);
      if (!mealKey) {
        return;
      }
      setEstimateBuilderMealOverrideDrafts((previous) => ({
        ...previous,
        [mealKey]: {
          ...(previous[mealKey] || {
            override_price: '',
            adults: '',
            kids: '',
          }),
          [field]: value,
        },
      }));
    },
    [],
  );

  const applyEstimateBuilderMealPriceOverride = useCallback(() => {
    const draft =
      estimateBuilderMealOverrideDrafts[activeEstimateBuilderMealKey] ||
      activeEstimateBuilderMealDraft;
    const parsedValue = parseNonNegativeDecimalInput(draft.override_price);
    if (Number.isNaN(parsedValue)) {
      Alert.alert('Invalid override', 'Override per guest must be a non-negative number.');
      return;
    }
    const mealName = activeEstimateBuilderMeal || 'Signature Menu';
    const mealKey = normalizeEstimateMealKey(mealName);
    const nextValue = parsedValue == null ? '' : parsedValue.toFixed(2);
    updateEstimateBuilderMealOverrideDraft(mealName, 'override_price', nextValue);
    setEstimateBuilderEstimate((previous) => {
      if (!previous) {
        return previous;
      }
      const nextTotals = { ...(previous.manual_meal_totals || {}) };
      for (const existingMealName of Object.keys(nextTotals)) {
        if (normalizeEstimateMealKey(existingMealName) === mealKey) {
          delete nextTotals[existingMealName];
        }
      }
      if (nextValue) {
        nextTotals[mealName] = nextValue;
      }
      return {
        ...previous,
        manual_meal_totals: nextTotals,
      };
    });
  }, [
    activeEstimateBuilderMeal,
    activeEstimateBuilderMealDraft,
    activeEstimateBuilderMealKey,
    estimateBuilderMealOverrideDrafts,
    updateEstimateBuilderMealOverrideDraft,
  ]);

  const applyEstimateBuilderMealGuestOverride = useCallback(() => {
    const draft =
      estimateBuilderMealOverrideDrafts[activeEstimateBuilderMealKey] ||
      activeEstimateBuilderMealDraft;
    const parsedAdults = parseNonNegativeIntegerInput(draft.adults);
    if (Number.isNaN(parsedAdults)) {
      Alert.alert('Invalid guest count', 'Adults override must be a non-negative whole number.');
      return;
    }
    const parsedKids = parseNonNegativeIntegerInput(draft.kids);
    if (Number.isNaN(parsedKids)) {
      Alert.alert('Invalid guest count', 'Kids override must be a non-negative whole number.');
      return;
    }
    const mealName = activeEstimateBuilderMeal || 'Signature Menu';
    const mealKey = normalizeEstimateMealKey(mealName);
    const adultsValue = parsedAdults == null ? '' : String(parsedAdults);
    const kidsValue = parsedKids == null ? '' : String(parsedKids);
    updateEstimateBuilderMealOverrideDraft(mealName, 'adults', adultsValue);
    updateEstimateBuilderMealOverrideDraft(mealName, 'kids', kidsValue);
    setEstimateBuilderEstimate((previous) => {
      if (!previous) {
        return previous;
      }
      const nextOverrides = { ...(previous.meal_guest_overrides || {}) };
      for (const existingMealName of Object.keys(nextOverrides)) {
        if (normalizeEstimateMealKey(existingMealName) === mealKey) {
          delete nextOverrides[existingMealName];
        }
      }
      if (parsedAdults != null || parsedKids != null) {
        nextOverrides[mealName] = {};
        if (parsedAdults != null) {
          nextOverrides[mealName].adults = parsedAdults;
        }
        if (parsedKids != null) {
          nextOverrides[mealName].kids = parsedKids;
        }
      }
      return {
        ...previous,
        meal_guest_overrides: nextOverrides,
      };
    });
  }, [
    activeEstimateBuilderMeal,
    activeEstimateBuilderMealDraft,
    activeEstimateBuilderMealKey,
    estimateBuilderMealOverrideDrafts,
    updateEstimateBuilderMealOverrideDraft,
  ]);

  const toggleEstimateBuilderMenuItem = useCallback(
    (item: EstimateBuilderMenuItem) => {
      const mealName = activeEstimateBuilderMeal || 'Signature Menu';
      const key = `${item.id}|${mealName.toLowerCase()}`;
      setEstimateBuilderMenuChoices((previous) => {
        const index = previous.findIndex(
          (row) => `${row.menu_item_id}|${row.meal_name.toLowerCase()}` === key,
        );
        if (index >= 0) {
          return previous.filter((_, rowIndex) => rowIndex !== index);
        }
        return [
          ...previous,
          {
            menu_item_id: item.id,
            meal_name: mealName,
            servings_per_person: item.default_servings_per_person || '1.00',
            notes: '',
            included: true,
          },
        ];
      });
    },
    [activeEstimateBuilderMeal],
  );

  const updateEstimateBuilderMenuChoice = useCallback(
    (menuItemId: number, field: 'servings_per_person' | 'notes', value: string) => {
      const mealName = activeEstimateBuilderMeal || 'Signature Menu';
      const key = `${menuItemId}|${mealName.toLowerCase()}`;
      setEstimateBuilderMenuChoices((previous) =>
        previous.map((row) => {
          const rowKey = `${row.menu_item_id}|${row.meal_name.toLowerCase()}`;
          if (rowKey !== key) return row;
          return {
            ...row,
            [field]: value,
          };
        }),
      );
    },
    [activeEstimateBuilderMeal],
  );

  const toggleEstimateBuilderExtraItem = useCallback((item: EstimateBuilderExtraItem) => {
    setEstimateBuilderExtraLines((previous) => {
      const index = previous.findIndex((row) => row.extra_item_id === item.id);
      if (index >= 0) {
        return previous.filter((row) => row.extra_item_id !== item.id);
      }
      return [
        ...previous,
        {
          extra_item_id: item.id,
          quantity: '1',
          override_price: '',
          notes: '',
          included: true,
        },
      ];
    });
  }, []);

  const updateEstimateBuilderExtraLine = useCallback(
    (itemId: number, field: 'quantity' | 'override_price' | 'notes', value: string) => {
      setEstimateBuilderExtraLines((previous) =>
        previous.map((row) =>
          row.extra_item_id === itemId
            ? {
                ...row,
                [field]: value,
              }
            : row,
        ),
      );
    },
    [],
  );

  const handleCreateShoppingList = useCallback(async () => {
    if (!token) {
      return;
    }
    const estimateId = shoppingEstimateRefId;
    let catererId = shoppingCatererId;
    if (estimateId) {
      const linked = estimates.find((row) => row.id === estimateId);
      if (linked) {
        catererId = linked.caterer_id;
      }
    }
    setCreatingShoppingList(true);
    try {
      const response = await fetch(apiUrl(apiBaseUrl, '/api/xpenz/shopping-lists/'), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: shoppingListTitle.trim(),
          caterer_id: catererId,
          estimate_id: estimateId,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false || !payload.shopping_list) {
        throw new Error(payload.error || 'Unable to create shopping list.');
      }
      setShoppingListTitle('');
      setShoppingEstimateRefId(null);
      if (catererChoices.length === 1) {
        setShoppingCatererId(catererChoices[0].id);
      }
      await loadShoppingLists();
      setSelectedShoppingList(payload.shopping_list);
      setShoppingListScreenMode('manage');
      await Promise.all([
        loadShoppingListDetail(payload.shopping_list.id),
        loadShoppingCatalog(),
      ]);
    } catch (error) {
      Alert.alert(
        'Create list failed',
        error instanceof Error ? error.message : 'Unable to create shopping list.',
      );
    } finally {
      setCreatingShoppingList(false);
    }
  }, [
    apiBaseUrl,
    catererChoices,
    estimates,
    loadShoppingCatalog,
    loadShoppingListDetail,
    loadShoppingLists,
    shoppingCatererId,
    shoppingEstimateRefId,
    shoppingListTitle,
    token,
  ]);

  const openShoppingList = useCallback(
    async (shoppingList: ShoppingListRow) => {
      setSelectedShoppingList(shoppingList);
      setShoppingListScreenMode('manage');
      try {
        await Promise.all([
          loadShoppingListDetail(shoppingList.id),
          loadShoppingCatalog(),
        ]);
      } catch (error) {
        Alert.alert(
          'Load error',
          error instanceof Error ? error.message : 'Unable to load shopping list.',
        );
      }
    },
    [loadShoppingCatalog, loadShoppingListDetail],
  );

  const submitShoppingItem = useCallback(
    async (
      itemNameRaw: string,
      itemTypeRaw: string,
      quantityRaw: string,
      itemUnitRaw: string,
    ) => {
      if (!selectedShoppingList || !token) {
        return false;
      }
      const itemName = itemNameRaw.trim();
      if (!itemName) {
        Alert.alert('Missing item', 'Enter the shopping item name.');
        return false;
      }

      setAddingShoppingItem(true);
      try {
        const response = await fetch(
          apiUrl(apiBaseUrl, `/api/xpenz/shopping-lists/${selectedShoppingList.id}/items/`),
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              item_name: itemName,
              item_type: itemTypeRaw.trim(),
              quantity: quantityRaw.trim() || '1',
              item_unit: itemUnitRaw.trim(),
            }),
          },
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || 'Unable to add shopping item.');
        }
        await Promise.all([
          loadShoppingListDetail(selectedShoppingList.id, undefined, undefined, true),
          loadShoppingLists(),
          loadShoppingCatalog(),
        ]);
        return true;
      } catch (error) {
        Alert.alert(
          'Add item failed',
          error instanceof Error ? error.message : 'Unable to add shopping item.',
        );
        return false;
      } finally {
        setAddingShoppingItem(false);
      }
    },
    [apiBaseUrl, loadShoppingCatalog, loadShoppingListDetail, loadShoppingLists, selectedShoppingList, token],
  );

  const openSavedItemQuickAdd = useCallback(
    (item: ShoppingCatalogListItem) => {
      const itemKey = item.item_name.trim().toLowerCase();
      if (!itemKey) return;
      if (savedItemExpandedKey === itemKey) {
        setSavedItemExpandedKey(null);
        setSavedItemQuickUnitPickerOpen(false);
        return;
      }
      setSavedItemExpandedKey(itemKey);
      setSavedItemQuickQty(savedItemLastQtyByKey[itemKey] || '1');
      setSavedItemQuickUnit(
        (item.last_used_unit || item.unit_options?.[0] || DEFAULT_SHOPPING_UNIT_OPTIONS[0] || '').trim(),
      );
      setSavedItemQuickType((item.type_options?.[0] || '').trim());
      setSavedItemQuickUnitPickerOpen(false);
    },
    [savedItemExpandedKey, savedItemLastQtyByKey],
  );

  const openCustomSavedItemQuickAdd = useCallback(() => {
    const rawName = savedItemSearchText.trim();
    if (!rawName) return;
    const itemKey = rawName.toLowerCase();
    if (savedItemExpandedKey === '__new__') {
      setSavedItemExpandedKey(null);
      setSavedItemQuickUnitPickerOpen(false);
      return;
    }
    setSavedItemExpandedKey('__new__');
    setSavedItemQuickQty(savedItemLastQtyByKey[itemKey] || '1');
    setSavedItemQuickUnit(DEFAULT_SHOPPING_UNIT_OPTIONS[0] || 'Pieces');
    setSavedItemQuickType('');
    setSavedItemQuickUnitPickerOpen(false);
  }, [savedItemExpandedKey, savedItemLastQtyByKey, savedItemSearchText]);

  const stepSavedItemQuickQty = useCallback(
    (delta: number) => {
      const current = Number.parseFloat(savedItemQuickQty || '0');
      const base = Number.isFinite(current) ? current : 0;
      const next = Math.max(0, base + delta);
      if (Number.isInteger(next)) {
        setSavedItemQuickQty(String(next));
      } else {
        setSavedItemQuickQty(next.toFixed(2).replace(/\.00$/, ''));
      }
    },
    [savedItemQuickQty],
  );

  const handleQuickAddSavedItem = useCallback(
    async (item: ShoppingCatalogListItem | null) => {
      const customName = savedItemSearchText.trim();
      const itemName = (item?.item_name || (savedItemExpandedKey === '__new__' ? customName : '')).trim();
      if (!itemName) {
        Alert.alert('Missing item', 'Type an item name to continue.');
        return;
      }
      const itemKey = itemName.toLowerCase();
      const quantity = (savedItemQuickQty || savedItemLastQtyByKey[itemKey] || '1').trim() || '1';
      const unit = (
        savedItemQuickUnit ||
        item?.last_used_unit ||
        item?.unit_options?.[0] ||
        shoppingAllUnitOptions[0] ||
        ''
      )
        .trim();
      const itemType = (savedItemQuickType || item?.type_options?.[0] || '').trim();
      const added = await submitShoppingItem(itemName, itemType, quantity, unit);
      if (!added) {
        return;
      }
      setSavedItemLastQtyByKey((prev) => ({
        ...prev,
        [itemKey]: quantity,
      }));
      setSavedItemExpandedKey(null);
      setSavedItemQuickUnitPickerOpen(false);
      setSavedItemSearchText('');
      requestAnimationFrame(() => {
        savedItemSearchInputRef.current?.focus();
      });
    },
    [
      savedItemExpandedKey,
      savedItemLastQtyByKey,
      savedItemQuickQty,
      savedItemQuickType,
      savedItemQuickUnit,
      savedItemSearchText,
      shoppingAllUnitOptions,
      submitShoppingItem,
    ],
  );

  const renderSavedItemQuickAddRow = useCallback(
    (item: ShoppingCatalogListItem | null, itemKey: string) => {
      if (savedItemExpandedKey !== itemKey) return null;
      return (
        <View style={styles.savedQuickAddWrap}>
          <View style={styles.savedQuickAddMainRow}>
            <Pressable style={styles.savedQuickQtyStepButton} onPress={() => stepSavedItemQuickQty(-1)}>
              <Text style={styles.savedQuickQtyStepButtonText}>−</Text>
            </Pressable>
            <TextInput
              style={styles.savedQuickQtyInput}
              value={savedItemQuickQty}
              onChangeText={setSavedItemQuickQty}
              keyboardType="decimal-pad"
              inputAccessoryViewID={Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined}
              placeholder="1"
            />
            <Pressable style={styles.savedQuickQtyStepButton} onPress={() => stepSavedItemQuickQty(1)}>
              <Text style={styles.savedQuickQtyStepButtonText}>+</Text>
            </Pressable>
            <Pressable
              style={styles.savedQuickUnitButton}
              onPress={() => setSavedItemQuickUnitPickerOpen((prev) => !prev)}
            >
              <Text style={styles.savedQuickUnitButtonText}>{savedItemQuickUnit || 'Unit'}</Text>
            </Pressable>
            <Pressable
              style={[styles.savedQuickAddButton, addingShoppingItem && styles.buttonDisabled]}
              onPress={() => handleQuickAddSavedItem(item)}
              disabled={addingShoppingItem}
            >
              {addingShoppingItem ? (
                <ActivityIndicator color="#ffffff" size="small" />
              ) : (
                <Text style={styles.savedQuickAddButtonText}>Add</Text>
              )}
            </Pressable>
          </View>
          {savedItemQuickUnitPickerOpen ? (
            <View style={styles.savedQuickUnitChips}>
              {quickAddUnitOptions.map((option) => {
                const selected = savedItemQuickUnit.trim().toLowerCase() === option.toLowerCase();
                return (
                  <Pressable
                    key={`${itemKey}-${option}`}
                    style={[styles.nativeChip, selected && styles.nativeChipSelected]}
                    onPress={() => {
                      setSavedItemQuickUnit(option);
                      setSavedItemQuickUnitPickerOpen(false);
                    }}
                  >
                    <Text style={[styles.nativeChipLabel, selected && styles.nativeChipLabelSelected]}>
                      {option}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ) : null}
        </View>
      );
    },
    [
      addingShoppingItem,
      handleQuickAddSavedItem,
      quickAddUnitOptions,
      savedItemExpandedKey,
      savedItemQuickQty,
      savedItemQuickUnit,
      savedItemQuickUnitPickerOpen,
      stepSavedItemQuickQty,
    ],
  );

  const closeShoppingItemEditor = useCallback(() => {
    setShoppingItemEditorOpen(false);
    setShoppingEditingItemId(null);
    setShoppingEditName('');
    setShoppingEditType('');
    setShoppingEditQty('');
    setShoppingEditUnit('');
    setSavingShoppingEdit(false);
  }, []);

  const openShoppingItemEditor = useCallback((item: ShoppingItem) => {
    setShoppingEditingItemId(item.id);
    setShoppingEditName(item.item_name || '');
    setShoppingEditType(item.item_type || '');
    setShoppingEditQty(item.quantity || '');
    setShoppingEditUnit(item.item_unit || '');
    setShoppingItemEditorOpen(true);
  }, []);

  const saveShoppingItemEdit = useCallback(async () => {
    if (!selectedShoppingList || !token || !shoppingEditingItemId || savingShoppingEdit) {
      return;
    }
    setSavingShoppingEdit(true);
    try {
      const added = await submitShoppingItem(
        shoppingEditName,
        shoppingEditType,
        shoppingEditQty,
        shoppingEditUnit,
      );
      if (!added) {
        return;
      }
      const response = await fetch(
        apiUrl(
          apiBaseUrl,
          `/api/xpenz/shopping-lists/${selectedShoppingList.id}/items/${shoppingEditingItemId}/remove/`,
        ),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || 'Unable to replace shopping item.');
      }
      await Promise.all([
        loadShoppingListDetail(selectedShoppingList.id, undefined, undefined, true),
        loadShoppingLists(),
      ]);
      closeShoppingItemEditor();
      Alert.alert('Saved', 'Shopping item updated.');
    } catch (error) {
      Alert.alert(
        'Save failed',
        error instanceof Error ? error.message : 'Unable to update shopping item.',
      );
      setSavingShoppingEdit(false);
    } finally {
      setSavingShoppingEdit(false);
    }
  }, [
    apiBaseUrl,
    closeShoppingItemEditor,
    loadShoppingListDetail,
    loadShoppingLists,
    savingShoppingEdit,
    selectedShoppingList,
    shoppingEditName,
    shoppingEditQty,
    shoppingEditType,
    shoppingEditUnit,
    shoppingEditingItemId,
    submitShoppingItem,
    token,
  ]);

  const handleRemoveShoppingItem = useCallback(
    async (item: ShoppingItem) => {
      if (!selectedShoppingList || !token || removingShoppingItemId) {
        return;
      }
      setRemovingShoppingItemId(item.id);
      try {
        const response = await fetch(
          apiUrl(
            apiBaseUrl,
            `/api/xpenz/shopping-lists/${selectedShoppingList.id}/items/${item.id}/remove/`,
          ),
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
            },
          },
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || 'Unable to remove item.');
        }
        await Promise.all([
          loadShoppingListDetail(selectedShoppingList.id, undefined, undefined, true),
          loadShoppingLists(),
        ]);
      } catch (error) {
        Alert.alert(
          'Remove failed',
          error instanceof Error ? error.message : 'Unable to remove shopping item.',
        );
      } finally {
        setRemovingShoppingItemId(null);
      }
    },
    [apiBaseUrl, loadShoppingListDetail, loadShoppingLists, removingShoppingItemId, selectedShoppingList, token],
  );

  const handleDeleteShoppingList = useCallback((targetList: ShoppingListRow) => {
    if (!token || deletingShoppingListId) {
      return;
    }
    Alert.alert(
      'Delete shopping list?',
      `Delete "${targetList.title}"? This removes the list, but keeps item history in saved items.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeletingShoppingListId(targetList.id);
            try {
              const response = await fetch(
                apiUrl(
                  apiBaseUrl,
                  `/api/xpenz/shopping-lists/${targetList.id}/delete/`,
                ),
                {
                  method: 'POST',
                  headers: {
                    Authorization: `Bearer ${token}`,
                  },
                },
              );
              const payload = await response.json().catch(() => ({}));
              if (!response.ok || payload.ok === false) {
                throw new Error(payload.error || 'Unable to delete shopping list.');
              }
              if (selectedShoppingList?.id === targetList.id) {
                setSelectedShoppingList(null);
                setShoppingItems([]);
                setSavedItemSearchText('');
                setSavedItemExpandedKey(null);
                setSavedItemQuickUnitPickerOpen(false);
                setOpenCatalogCategory(null);
                setShoppingListScreenMode('manage');
              }
              await Promise.all([loadShoppingLists(), loadShoppingCatalog()]);
            } catch (error) {
              Alert.alert(
                'Delete failed',
                error instanceof Error ? error.message : 'Unable to delete shopping list.',
              );
            } finally {
              setDeletingShoppingListId(null);
            }
          },
        },
      ],
    );
  }, [
    apiBaseUrl,
    deletingShoppingListId,
    loadShoppingCatalog,
    loadShoppingLists,
    selectedShoppingList,
    token,
  ]);

  const plannerSuggestionsForField = useCallback(
    (
      section: PlannerSectionCode,
      groupCode: string,
      itemCode: string,
      fieldCode: string,
      currentValue = '',
    ) => {
      const exactKey = `${section}|${groupCode || ''}|${itemCode || ''}|${fieldCode}`;
      const groupKey = `${section}|${groupCode || ''}||${fieldCode}`;
      const sectionKey = `${section}|||${fieldCode}`;
      return mergeOptionValues(
        plannerMemoryMap.get(exactKey),
        plannerMemoryMap.get(groupKey),
        plannerMemoryMap.get(sectionKey),
        [currentValue],
      );
    },
    [plannerMemoryMap],
  );

  const closePlannerEditor = useCallback(() => {
    setPlannerEditorVisible(false);
    setPlannerEditingEntryId(null);
    setPlannerEditorGroupCode('');
    setPlannerEditorItemCode('');
    setPlannerEditorValues({});
    setPlannerEditorFieldDraftValues({});
    setPlannerEditorNotes('');
    setPlannerEditorChecked(false);
    setPlannerEditorFieldCards([]);
    setPlannerFieldCardsManagerOpen(false);
    setPlannerNewOptionName('');
  }, []);

  const openPlannerEditor = useCallback(
    (entry?: PlannerEntryRow, preferredGroupCode?: string, preferredItemCode?: string) => {
      const activeSection = (entry?.section || plannerSection) as PlannerSectionCode | null;
      if (!activeSection) {
        return;
      }
      const sectionConfig = plannerConfigForActive(activeSection);
      if (!sectionConfig) {
        return;
      }
      const nextGroupCode =
        entry?.group_code || preferredGroupCode || sectionConfig.groups[0]?.code || '';
      const groupConfig = plannerGroupForActive(activeSection, nextGroupCode);
      const requestedItemCode = entry?.item_code || preferredItemCode || '';
      const itemExists = groupConfig?.itemOptions?.some((row) => row.code === requestedItemCode);
      const keepBaseCardSelected = !requestedItemCode && !!groupConfig?.showGroupCard;
      const nextItemCode = keepBaseCardSelected
        ? ''
        : itemExists
          ? requestedItemCode
          : groupConfig?.itemOptions?.[0]?.code || '';
      const editorFields = plannerFieldsForActive(activeSection, nextGroupCode, nextItemCode);
      const rawValues = (entry?.data || {}) as Record<string, string>;
      const cardKey = `${activeSection}|${nextGroupCode}|${nextItemCode}`;
      const persistedCards = [...(plannerFieldCardMap.get(cardKey) || [])].sort(
        (a, b) =>
          (a.sort_order || 0) - (b.sort_order || 0) ||
          (a.field_label || '').localeCompare(b.field_label || ''),
      );
      const persistedByCode = new Map<string, PlannerFieldCardRow>();
      for (const row of persistedCards) {
        const code = normalizePlannerCode(row.field_code || row.field_label || '');
        if (!code || persistedByCode.has(code)) {
          continue;
        }
        persistedByCode.set(code, row);
      }

      const editorFieldCards: PlannerEditorFieldCard[] = [];
      const presetFieldCodes = new Set<string>();
      const addEditorFieldCard = (
        fieldCode: string,
        fieldLabel: string,
        valueOptionsText = '',
        sortOrder?: number,
      ) => {
        const normalizedCode = normalizePlannerCode(fieldCode || fieldLabel);
        if (!normalizedCode) {
          return;
        }
        if (presetFieldCodes.has(normalizedCode)) {
          return;
        }
        presetFieldCodes.add(normalizedCode);
        editorFieldCards.push({
          id: localId(),
          fieldCode: normalizedCode,
          fieldLabel: fieldLabel || humanizePlannerCode(normalizedCode),
          valueOptionsText,
          sortOrder:
            Number.isFinite(sortOrder as number) && (sortOrder as number) >= 0
              ? Number(sortOrder)
              : editorFieldCards.length,
        });
      };

      for (const field of editorFields) {
        const normalizedCode = normalizePlannerCode(field.code || field.label || '');
        if (!normalizedCode) {
          continue;
        }
        const persisted = persistedByCode.get(normalizedCode);
        addEditorFieldCard(
          normalizedCode,
          (persisted?.field_label || '').trim() || field.label || humanizePlannerCode(normalizedCode),
          mergeOptionValues(
            field.valueOptions,
            persisted?.value_options,
          ).join(', '),
          persisted?.sort_order,
        );
      }

      for (const persisted of persistedCards) {
        addEditorFieldCard(
          persisted.field_code || persisted.field_label || '',
          persisted.field_label || humanizePlannerCode(persisted.field_code || ''),
          mergeOptionValues(persisted.value_options || []).join(', '),
          persisted.sort_order,
        );
      }

      const presetValues: Record<string, string> = {};
      for (const card of editorFieldCards) {
        const fieldCode = normalizePlannerCode(card.fieldCode || card.fieldLabel);
        if (!fieldCode) {
          continue;
        }
        presetValues[fieldCode] = rawValues[fieldCode] || '';
      }
      for (const [key, value] of Object.entries(rawValues)) {
        const normalizedCode = normalizePlannerCode(key);
        if (!normalizedCode) {
          continue;
        }
        presetValues[normalizedCode] = value || '';
        addEditorFieldCard(
          normalizedCode,
          humanizePlannerCode(key) || key,
          mergeOptionValues([value || '']).join(', '),
        );
      }
      setPlannerEditingEntryId(entry?.id || null);
      setPlannerEditorGroupCode(nextGroupCode);
      setPlannerEditorItemCode(nextItemCode);
      setPlannerEditorValues(presetValues);
      setPlannerEditorFieldDraftValues({});
      setPlannerEditorNotes(entry?.notes || '');
      setPlannerEditorChecked(entry?.is_checked || false);
      setPlannerEditorFieldCards(
        editorFieldCards
          .sort((a, b) => a.sortOrder - b.sortOrder)
          .map((row, index) => ({ ...row, sortOrder: index })),
      );
      setPlannerFieldCardsManagerOpen(false);
      setPlannerEditorVisible(true);
    },
    [
      plannerConfigForActive,
      plannerFieldCardMap,
      plannerFieldsForActive,
      plannerGroupForActive,
      plannerSection,
    ],
  );

  const openPlannerGroupCard = useCallback(
    (groupCode: string, itemCode = '', existingEntry?: PlannerEntryRow) => {
      if (existingEntry) {
        openPlannerEditor(existingEntry);
        return;
      }
      openPlannerEditor(undefined, groupCode, itemCode);
    },
    [openPlannerEditor],
  );

  const activePlannerSectionConfig = useMemo(
    () => plannerConfigForActive(plannerSection),
    [plannerConfigForActive, plannerSection],
  );

  const activePlannerEditorGroup = useMemo(
    () => plannerGroupForActive(plannerSection, plannerEditorGroupCode),
    [plannerEditorGroupCode, plannerGroupForActive, plannerSection],
  );

  const activePlannerEditorFields = useMemo(() => {
    const baseFields = plannerFieldsForActive(plannerSection, plannerEditorGroupCode, plannerEditorItemCode);
    const baseFieldMap = new Map<string, PlannerFieldConfig>();
    for (const field of baseFields) {
      const normalizedCode = normalizePlannerCode(field.code || field.label || '');
      if (!normalizedCode || baseFieldMap.has(normalizedCode)) {
        continue;
      }
      baseFieldMap.set(normalizedCode, { ...field, code: normalizedCode });
    }

    const cards = [...plannerEditorFieldCards].sort((a, b) => a.sortOrder - b.sortOrder);
    const mergedFields: PlannerFieldConfig[] = [];
    const seen = new Set<string>();
    const pushField = (fieldCode: string, fieldLabel = '', valueOptions: string[] = []) => {
      const normalizedCode = normalizePlannerCode(fieldCode || fieldLabel);
      if (!normalizedCode || seen.has(normalizedCode)) {
        return;
      }
      seen.add(normalizedCode);
      const baseField = baseFieldMap.get(normalizedCode) || PLANNER_FIELD_TEMPLATE_MAP.get(normalizedCode);
      const resolvedLabel = fieldLabel || baseField?.label || humanizePlannerCode(normalizedCode);
      mergedFields.push({
        ...(baseField || {}),
        code: normalizedCode,
        label: resolvedLabel,
        placeholder: resolvedLabel,
        valueOptions: mergeOptionValues(baseField?.valueOptions, valueOptions),
      });
    };

    for (const row of cards) {
      pushField(
        row.fieldCode || row.fieldLabel,
        row.fieldLabel.trim(),
        plannerSplitMultiValue(row.valueOptionsText || ''),
      );
    }
    for (const field of baseFields) {
      pushField(field.code, field.label, field.valueOptions || []);
    }
    return mergedFields;
  }, [
    plannerEditorFieldCards,
    plannerEditorGroupCode,
    plannerEditorItemCode,
    plannerFieldsForActive,
    plannerSection,
  ]);

  const activePlannerEditorOptionLabel = useMemo(
    () =>
      activePlannerEditorGroup?.itemOptions?.find((option) => option.code === plannerEditorItemCode)
        ?.label || '',
    [activePlannerEditorGroup, plannerEditorItemCode],
  );

  const addPlannerOptionToGroup = useCallback(async () => {
    if (!plannerSection || !plannerCategoryCode || !selectedPlannerEstimate || !token) {
      return;
    }
    const label = plannerNewOptionName.trim();
    if (!label) {
      Alert.alert('Missing option name', 'Enter an option name first.');
      return;
    }
    const optionCode = normalizePlannerCode(label);
    if (!optionCode) {
      Alert.alert('Invalid option name', 'Use letters or numbers in the option name.');
      return;
    }

    const groupConfig = plannerGroupForActive(plannerSection, plannerCategoryCode);
    const exists = (groupConfig?.itemOptions || []).some((row) => row.code === optionCode);
    if (exists) {
      Alert.alert('Option exists', 'That option already exists for this category.');
      return;
    }

    setSavingPlanner(true);
    try {
      const response = await fetch(
        apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedPlannerEstimate.id}/planner/`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'save_option_card',
            section: plannerSection,
            group_code: plannerCategoryCode,
            item_code: optionCode,
            item_label: label,
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || 'Unable to add planner option.');
      }
      if (Array.isArray(payload.item_catalog)) {
        setPlannerItemCatalog(payload.item_catalog);
      } else {
        setPlannerItemCatalog((prev) => {
          const alreadyExists = prev.some(
            (row) =>
              row.section === plannerSection &&
              row.group_code === plannerCategoryCode &&
              row.item_code === optionCode,
          );
          if (alreadyExists) {
            return prev;
          }
          return [
            ...prev,
            {
              section: plannerSection,
              group_code: plannerCategoryCode,
              item_code: optionCode,
              item_label: label,
              usage_count: 0,
            },
          ];
        });
      }
      setPlannerNewOptionName('');
    } catch (error) {
      Alert.alert(
        'Add option failed',
        error instanceof Error ? error.message : 'Unable to add planner option.',
      );
    } finally {
      setSavingPlanner(false);
    }
  }, [
    apiBaseUrl,
    plannerCategoryCode,
    plannerGroupForActive,
    plannerNewOptionName,
    plannerSection,
    selectedPlannerEstimate,
    token,
  ]);

  const addPlannerEditorFieldCard = useCallback(() => {
    setPlannerEditorFieldCards((prev) => [
      ...prev,
      {
        id: localId(),
        fieldCode: '',
        fieldLabel: '',
        valueOptionsText: '',
        sortOrder: prev.length,
      },
    ]);
  }, []);

  const movePlannerEditorFieldCard = useCallback((id: string, direction: 'up' | 'down') => {
    setPlannerEditorFieldCards((prev) => {
      const index = prev.findIndex((row) => row.id === id);
      if (index < 0) {
        return prev;
      }
      const targetIndex = direction === 'up' ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= prev.length) {
        return prev;
      }
      const next = [...prev];
      const [moved] = next.splice(index, 1);
      next.splice(targetIndex, 0, moved);
      return next.map((row, rowIndex) => ({ ...row, sortOrder: rowIndex }));
    });
  }, []);

  const updatePlannerEditorFieldCard = useCallback(
    (id: string, patch: Partial<PlannerEditorFieldCard>) => {
      setPlannerEditorFieldCards((prev) =>
        prev.map((row) =>
          row.id === id
            ? {
                ...row,
                ...patch,
              }
            : row,
        ),
      );
    },
    [],
  );

  const deletePlannerEditorFieldCard = useCallback((id: string) => {
    setPlannerEditorFieldCards((prev) =>
      prev
        .filter((row) => row.id !== id)
        .map((row, rowIndex) => ({ ...row, sortOrder: rowIndex })),
    );
  }, []);

  const replacePlannerFieldCardsForEditorKey = useCallback(
    (rows: PlannerFieldCardRow[]) => {
      if (!plannerSection || !plannerEditorGroupCode) {
        return;
      }
      const normalizedItemCode = (plannerEditorItemCode || '').trim();
      setPlannerFieldCards((prev) => {
        const kept = prev.filter(
          (row) =>
            !(
              row.section === plannerSection &&
              (row.group_code || '').trim() === plannerEditorGroupCode &&
              (row.item_code || '').trim() === normalizedItemCode
            ),
        );
        return [...kept, ...rows];
      });
    },
    [plannerEditorGroupCode, plannerEditorItemCode, plannerSection],
  );

  const persistPlannerFieldCards = useCallback(
    async (
      fieldCardsPayload: PlannerFieldCardPayloadRow[],
      options?: { allowInactiveEndpoint?: boolean },
    ) => {
      if (!selectedPlannerEstimate || !plannerSection || !token || !plannerEditorGroupCode) {
        throw new Error('Planner context is missing. Re-open the option and try again.');
      }
      const cardsResponse = await fetch(
        apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedPlannerEstimate.id}/planner/`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'save_field_cards',
            section: plannerSection,
            group_code: plannerEditorGroupCode,
            item_code: plannerEditorItemCode,
            field_cards: fieldCardsPayload,
          }),
        },
      );
      const cardsPayload = await cardsResponse.json().catch(() => ({}));
      if (isPlannerFieldCardsEndpointInactive(cardsResponse.ok, cardsResponse.status, cardsPayload)) {
        if (options?.allowInactiveEndpoint) {
          return { endpointInactive: true, savedCards: [] as PlannerFieldCardRow[] };
        }
        throw new Error(
          'Variable cards endpoint is not active on the server yet. Deploy backend updates and retry.',
        );
      }
      if (!cardsResponse.ok || cardsPayload.ok === false) {
        throw new Error(
          cardsPayload.error ||
            'Variable cards could not be saved. Backend deploy/migration may be missing.',
        );
      }
      const savedCards = Array.isArray(cardsPayload.field_cards)
        ? (cardsPayload.field_cards as PlannerFieldCardRow[])
        : [];
      replacePlannerFieldCardsForEditorKey(savedCards);
      return { endpointInactive: false, savedCards };
    },
    [
      apiBaseUrl,
      plannerEditorGroupCode,
      plannerEditorItemCode,
      plannerSection,
      replacePlannerFieldCardsForEditorKey,
      selectedPlannerEstimate,
      token,
    ],
  );

  const savePlannerFieldCardEdits = useCallback(async () => {
    const { cards: fieldCardsPayload, validationError } = buildPlannerFieldCardsPayload(
      plannerEditorFieldCards,
    );
    if (validationError) {
      Alert.alert('Missing field name', validationError);
      return;
    }
    setSavingPlanner(true);
    try {
      await persistPlannerFieldCards(fieldCardsPayload);
      setPlannerFieldCardsManagerOpen(false);
    } catch (error) {
      Alert.alert('Save failed', error instanceof Error ? error.message : 'Unable to save variable cards.');
    } finally {
      setSavingPlanner(false);
    }
  }, [persistPlannerFieldCards, plannerEditorFieldCards]);

  const handleSelectPlannerEstimate = useCallback(
    async (estimate: EstimateRow) => {
      setSelectedPlannerEstimate(estimate);
      setPlannerSection(null);
      setPlannerCategoryCode('');
      setPlannerSearchText('');
      setPlannerItemCatalog([]);
      setPlannerIconOverrides([]);
      setPlannerFieldCards([]);
      try {
        await loadPlannerData(estimate.id);
      } catch (error) {
        Alert.alert(
          'Load error',
          error instanceof Error ? error.message : 'Unable to load planner board.',
        );
      }
    },
    [loadPlannerData],
  );

  const savePlannerEntry = useCallback(async () => {
    if (!selectedPlannerEstimate || !plannerSection || !token || !plannerEditorGroupCode) {
      return;
    }
    const payloadData: Record<string, string> = {};
    for (const field of activePlannerEditorFields) {
      const value = (plannerEditorValues[field.code] || '').trim();
      if (!value) continue;
      payloadData[field.code] = value;
    }
    const { cards: fieldCardsPayload, validationError } = buildPlannerFieldCardsPayload(
      plannerEditorFieldCards,
    );
    if (validationError) {
      Alert.alert('Missing field name', validationError);
      return;
    }

    setSavingPlanner(true);
    try {
      const response = await fetch(
        apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedPlannerEstimate.id}/planner/`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            action: 'upsert',
            entry_id: plannerEditingEntryId || undefined,
            section: plannerSection,
            group_code: plannerEditorGroupCode,
            item_code: plannerEditorItemCode,
            item_label: activePlannerEditorOptionLabel || undefined,
            data: payloadData,
            notes: plannerEditorNotes.trim(),
            is_checked: plannerEditorChecked,
            sort_order: plannerEditingEntryId ? undefined : plannerEntriesForSection.length,
            field_cards: fieldCardsPayload,
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || 'Unable to save planner item.');
      }
      let endpointInactive = false;
      if (fieldCardsPayload.length) {
        const cardsResult = await persistPlannerFieldCards(fieldCardsPayload, {
          allowInactiveEndpoint: true,
        });
        endpointInactive = cardsResult.endpointInactive;
      }
      await loadPlannerData(selectedPlannerEstimate.id);
      closePlannerEditor();
      if (endpointInactive) {
        Alert.alert(
          'Saved with warning',
          'Planner item was saved, but variable cards could not sync because the backend endpoint is not active yet.',
        );
      }
    } catch (error) {
      Alert.alert('Save failed', error instanceof Error ? error.message : 'Unable to save planner item.');
    } finally {
      setSavingPlanner(false);
    }
  }, [
    activePlannerEditorFields,
    apiBaseUrl,
    closePlannerEditor,
    loadPlannerData,
    plannerEditorChecked,
    plannerEditorFieldCards,
    plannerEditingEntryId,
    persistPlannerFieldCards,
    plannerEditorGroupCode,
    plannerEditorItemCode,
    plannerEditorNotes,
    plannerEditorValues,
    plannerEntriesForSection.length,
    plannerSection,
    activePlannerEditorOptionLabel,
    selectedPlannerEstimate,
    token,
  ]);

  const deletePlannerEntry = useCallback(
    async (entry: PlannerEntryRow) => {
      if (!selectedPlannerEstimate || !token) {
        return;
      }
      Alert.alert(
        'Delete planner item?',
        'This row will be removed from the planning checklist.',
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: async () => {
              setSavingPlanner(true);
              try {
                const response = await fetch(
                  apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedPlannerEstimate.id}/planner/`),
                  {
                    method: 'POST',
                    headers: {
                      Authorization: `Bearer ${token}`,
                      'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                      action: 'delete',
                      entry_id: entry.id,
                    }),
                  },
                );
                const payload = await response.json().catch(() => ({}));
                if (!response.ok || payload.ok === false) {
                  throw new Error(payload.error || 'Unable to delete planner item.');
                }
                await loadPlannerData(selectedPlannerEstimate.id);
              } catch (error) {
                Alert.alert(
                  'Delete failed',
                  error instanceof Error ? error.message : 'Unable to delete planner item.',
                );
              } finally {
                setSavingPlanner(false);
              }
            },
          },
        ],
      );
    },
    [apiBaseUrl, loadPlannerData, selectedPlannerEstimate, token],
  );

  const togglePlannerChecked = useCallback(
    async (entry: PlannerEntryRow) => {
      if (!selectedPlannerEstimate || !token) {
        return;
      }
      setSavingPlanner(true);
      try {
        const response = await fetch(
          apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedPlannerEstimate.id}/planner/`),
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              action: 'upsert',
              entry_id: entry.id,
              section: entry.section,
              group_code: entry.group_code,
              item_code: entry.item_code,
              data: entry.data || {},
              notes: entry.notes || '',
              is_checked: !entry.is_checked,
              sort_order: entry.sort_order || 0,
            }),
          },
        );
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || 'Unable to update checklist item.');
        }
        await loadPlannerData(selectedPlannerEstimate.id);
      } catch (error) {
        Alert.alert(
          'Update failed',
          error instanceof Error ? error.message : 'Unable to update checklist item.',
        );
      } finally {
        setSavingPlanner(false);
      }
    },
    [apiBaseUrl, loadPlannerData, selectedPlannerEstimate, token],
  );

  const addManualDraft = useCallback(() => {
    setDrafts((prev) => [
      {
        localId: localId(),
        manualOnly: true,
        expenseText: '',
        expenseAmount: '',
        noteText: '',
      },
      ...prev,
    ]);
  }, []);

  const createDraftAndStartVoice = useCallback(
    async (captured: ImagePicker.ImagePickerAsset) => {
      const draftId = localId();
      setDrafts((prev) => [
        {
          localId: draftId,
          manualOnly: false,
          receiptUri: captured.uri,
          receiptFileName: captured.fileName || `receipt-${draftId}.jpg`,
          receiptMimeType: captured.mimeType || 'image/jpeg',
          expenseText: '',
          expenseAmount: '',
          noteText: '',
        },
        ...prev,
      ]);

      const { granted } = await requestRecordingPermissionsAsync();
      if (!granted) {
        Alert.alert('Microphone permission needed', 'Allow microphone access to record voice notes.');
        setActiveRecordingDraftId(null);
        setRecordingPhotoUri(null);
        return;
      }

      try {
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
        setActiveRecordingDraftId(draftId);
        setRecordingPhotoUri(captured.uri);
        setRecordingStartedAt(Date.now());
      } catch (error) {
        setActiveRecordingDraftId(null);
        setRecordingPhotoUri(null);
        Alert.alert(
          'Recording error',
          error instanceof Error ? error.message : 'Unable to start recording.',
        );
      }
    },
    [recorder],
  );

  const captureReceiptAndVoice = useCallback(async () => {
    if (isRecording) {
      Alert.alert('Recording in progress', 'Stop the current recording first.');
      return;
    }

    const cameraPerm = await ImagePicker.requestCameraPermissionsAsync();
    if (!cameraPerm.granted) {
      Alert.alert('Camera permission needed', 'Allow camera access to capture receipt images.');
      return;
    }

    const pickerResult = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.75,
    });
    if (pickerResult.canceled || !pickerResult.assets.length) {
      return;
    }
    await createDraftAndStartVoice(pickerResult.assets[0]);
  }, [createDraftAndStartVoice, isRecording]);

  const pickReceiptFromGalleryAndVoice = useCallback(async () => {
    if (isRecording) {
      Alert.alert('Recording in progress', 'Stop the current recording first.');
      return;
    }

    const mediaPerm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!mediaPerm.granted) {
      Alert.alert('Photos permission needed', 'Allow photo library access to choose receipt images.');
      return;
    }

    const pickerResult = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.75,
      allowsMultipleSelection: false,
    });
    if (pickerResult.canceled || !pickerResult.assets.length) {
      return;
    }
    await createDraftAndStartVoice(pickerResult.assets[0]);
  }, [createDraftAndStartVoice, isRecording]);

  const stopRecordingAndCreateDraft = useCallback(async () => {
    if (!recordingPhotoUri || !activeRecordingDraftId) {
      return;
    }

    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });

      const recorderStateNow = recorder.getStatus();
      const voiceUri = recorder.uri || recorderStateNow.url || null;

      const fallbackSeconds = recordingStartedAt
        ? Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
        : 1;
      const durationSeconds = recorderState.durationMillis
        ? Math.max(1, Math.round(recorderState.durationMillis / 1000))
        : fallbackSeconds;
      setDrafts((prev) =>
        prev.map((draft) =>
          draft.localId === activeRecordingDraftId
            ? {
                ...draft,
                voiceUri: voiceUri || undefined,
                voiceDurationSeconds: voiceUri ? durationSeconds : undefined,
              }
            : draft,
        ),
      );
      if (!voiceUri) {
        Alert.alert(
          'Voice note missing',
          'Receipt was added. Voice note was not attached, but you can still save this expense.',
        );
      }
      setRecordingPhotoUri(null);
      setRecordingStartedAt(null);
      setActiveRecordingDraftId(null);
    } catch (error) {
      Alert.alert(
        'Stop recording error',
        error instanceof Error ? error.message : 'Unable to stop recording.',
      );
    }
  }, [
    activeRecordingDraftId,
    recorder,
    recorderState.durationMillis,
    recordingPhotoUri,
    recordingStartedAt,
  ]);

  const cancelRecording = useCallback(async () => {
    try {
      if (isRecording) {
        await recorder.stop();
      }
    } catch {
      // Ignore stop errors during cancel.
    }
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    setRecordingPhotoUri(null);
    setRecordingStartedAt(null);
    setActiveRecordingDraftId(null);
  }, [isRecording, recorder]);

  const updateDraft = useCallback((id: string, patch: Partial<ExpenseDraft>) => {
    setDrafts((prev) => prev.map((draft) => (draft.localId === id ? { ...draft, ...patch } : draft)));
  }, []);

  const removeDraft = useCallback((id: string) => {
    setDrafts((prev) => prev.filter((draft) => draft.localId !== id));
  }, []);

  const uploadDrafts = useCallback(async () => {
    if (!selectedEstimate || !token) {
      Alert.alert('No job selected', 'Select an estimate first.');
      return;
    }
    if (!drafts.length) {
      Alert.alert('Nothing to save', 'Add at least one expense draft first.');
      return;
    }

    setUploading(true);
    try {
      for (let index = 0; index < drafts.length; index += 1) {
        const draft = drafts[index];

        if (!draft.manualOnly && !draft.receiptUri) {
          throw new Error(`Draft ${index + 1} is missing a receipt image.`);
        }

        const formData = new FormData();
        if (draft.manualOnly) {
          formData.append('is_manual_only', '1');
        }
        if (draft.expenseText.trim()) {
          formData.append('expense_text', draft.expenseText.trim());
        }
        if (draft.expenseAmount.trim()) {
          formData.append('expense_amount', draft.expenseAmount.trim());
        }
        if (draft.noteText.trim()) {
          formData.append('note_text', draft.noteText.trim());
        }
        if (draft.voiceDurationSeconds) {
          formData.append('voice_note_duration_seconds', String(draft.voiceDurationSeconds));
        }
        if (!draft.manualOnly && draft.receiptUri) {
          formData.append('receipt_image', {
            uri: draft.receiptUri,
            name: draft.receiptFileName || `receipt-${draft.localId}.jpg`,
            type: draft.receiptMimeType || 'image/jpeg',
          } as unknown as Blob);
        }
        if (!draft.manualOnly && draft.voiceUri) {
          formData.append('voice_note', {
            uri: draft.voiceUri,
            name: `voice-${draft.localId}.m4a`,
            type: 'audio/m4a',
          } as unknown as Blob);
        }

        const response = await fetch(
          apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedEstimate.id}/expenses/`),
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
            },
            body: formData,
          },
        );

        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok === false) {
          throw new Error(payload.error || `Failed on draft ${index + 1}.`);
        }
      }

      setDrafts([]);
      await loadEntries(selectedEstimate.id);
      await loadEstimates();
      Alert.alert('Saved', 'Expense entries were attached to this estimate.');
    } catch (error) {
      Alert.alert('Upload error', error instanceof Error ? error.message : 'Upload failed.');
    } finally {
      setUploading(false);
    }
  }, [apiBaseUrl, drafts, loadEntries, loadEstimates, selectedEstimate, token]);

  const applyStaffCostsToExpenses = useCallback(async () => {
    if (!selectedEstimate || !token) {
      return;
    }
    if (!selectedEstimate.can_manage_staff) {
      Alert.alert('No access', 'Your account cannot manage staff costs for this job.');
      return;
    }
    setApplyingStaffCosts(true);
    try {
      const response = await fetch(
        apiUrl(apiBaseUrl, `/api/xpenz/estimates/${selectedEstimate.id}/staff/apply-expense/`),
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || 'Unable to apply staff costs.');
      }
      await Promise.all([loadStaffSummary(selectedEstimate.id), loadEntries(selectedEstimate.id), loadEstimates()]);
      Alert.alert('Applied', `Moved ${formatShekel(payload.applied_total || '0.00')} to expenses.`);
    } catch (error) {
      Alert.alert('Apply failed', error instanceof Error ? error.message : 'Unable to apply staff costs.');
    } finally {
      setApplyingStaffCosts(false);
    }
  }, [apiBaseUrl, loadEntries, loadEstimates, loadStaffSummary, selectedEstimate, token]);

  const recordingSeconds = useMemo(() => {
    if (recorderState.durationMillis) {
      return Math.max(1, Math.round(recorderState.durationMillis / 1000));
    }
    if (recordingStartedAt) {
      return Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000));
    }
    return 0;
  }, [recorderState.durationMillis, recordingStartedAt]);

  const plannerApplySuggestion = useCallback(
    (fieldCode: string, suggestion: string) => {
      const code = fieldCode.toLowerCase();
      const isColorField = code.includes('color');
      setPlannerEditorValues((prev) => {
        if (isColorField) {
          const currentValues = plannerSplitMultiValue(prev[fieldCode] || '');
          const exists = currentValues.some(
            (value) => value.toLowerCase() === suggestion.toLowerCase(),
          );
          const nextValues = exists
            ? currentValues.filter((value) => value.toLowerCase() !== suggestion.toLowerCase())
            : [...currentValues, suggestion];
          return {
            ...prev,
            [fieldCode]: nextValues.join(', '),
          };
        }
        return {
          ...prev,
          [fieldCode]: suggestion,
        };
      });
    },
    [],
  );

  const plannerAddListFieldValue = useCallback((fieldCode: string, rawValue: string) => {
    const nextValue = (rawValue || '').trim();
    if (!nextValue) {
      return;
    }
    setPlannerEditorValues((prev) => {
      const currentValues = plannerSplitMultiValue(prev[fieldCode] || '');
      return {
        ...prev,
        [fieldCode]: mergeOptionValues(currentValues, [nextValue]).join(', '),
      };
    });
    setPlannerEditorFieldDraftValues((prev) => ({
      ...prev,
      [fieldCode]: '',
    }));
  }, []);

  const plannerToggleListFieldValue = useCallback((fieldCode: string, rawValue: string) => {
    const toggledValue = (rawValue || '').trim();
    if (!toggledValue) {
      return;
    }
    setPlannerEditorValues((prev) => {
      const currentValues = plannerSplitMultiValue(prev[fieldCode] || '');
      const exists = currentValues.some(
        (value) => value.toLowerCase() === toggledValue.toLowerCase(),
      );
      const nextValues = exists
        ? currentValues.filter((value) => value.toLowerCase() !== toggledValue.toLowerCase())
        : [...currentValues, toggledValue];
      return {
        ...prev,
        [fieldCode]: nextValues.join(', '),
      };
    });
  }, []);

  const plannerRemoveListFieldValue = useCallback((fieldCode: string, rawValue: string) => {
    const removedValue = (rawValue || '').trim();
    if (!removedValue) {
      return;
    }
    setPlannerEditorValues((prev) => {
      const currentValues = plannerSplitMultiValue(prev[fieldCode] || '');
      const nextValues = currentValues.filter(
        (value) => value.toLowerCase() !== removedValue.toLowerCase(),
      );
      return {
        ...prev,
        [fieldCode]: nextValues.join(', '),
      };
    });
  }, []);

  const plannerProgressBySection = useMemo(() => {
    const counters = new Map<PlannerSectionCode, { total: number; completed: number }>();
    for (const section of PLANNER_SECTION_CHOICES) {
      counters.set(section.code, { total: 0, completed: 0 });
    }
    for (const entry of plannerEntries) {
      const bucket = counters.get(entry.section);
      if (!bucket) {
        continue;
      }
      bucket.total += 1;
      if (entry.is_checked) {
        bucket.completed += 1;
      }
    }
    return counters;
  }, [plannerEntries]);

  const filteredEstimateBuilderMenuCategories = useMemo(() => {
    const categories = estimateBuilderCatalog?.menu_categories || [];
    const search = estimateBuilderMenuSearch.trim().toLowerCase();
    if (!search) return categories;
    return categories
      .map((category) => ({
        ...category,
        items: category.items.filter((item) => {
          const haystack = `${item.name} ${item.description}`.toLowerCase();
          return haystack.includes(search);
        }),
      }))
      .filter((category) => category.items.length > 0);
  }, [estimateBuilderCatalog, estimateBuilderMenuSearch]);

  const filteredEstimateBuilderDecorCategories = useMemo(() => {
    const categories = estimateBuilderCatalog?.extra_categories || [];
    const search = estimateBuilderExtrasSearch.trim().toLowerCase();
    return categories
      .filter((category) => category.code === 'DECOR' || category.code === 'RENTAL')
      .map((category) => ({
        ...category,
        items: category.items.filter((item) => {
          if (!search) return true;
          const haystack = `${item.name} ${item.notes}`.toLowerCase();
          return haystack.includes(search);
        }),
      }))
      .filter((category) => category.items.length > 0);
  }, [estimateBuilderCatalog, estimateBuilderExtrasSearch]);

  const filteredEstimateBuilderAddonCategories = useMemo(() => {
    const categories = estimateBuilderCatalog?.extra_categories || [];
    const search = estimateBuilderExtrasSearch.trim().toLowerCase();
    return categories
      .filter((category) => category.code === 'SERVICE' || category.code === 'OTHER')
      .map((category) => ({
        ...category,
        items: category.items.filter((item) => {
          if (!search) return true;
          const haystack = `${item.name} ${item.notes}`.toLowerCase();
          return haystack.includes(search);
        }),
      }))
      .filter((category) => category.items.length > 0);
  }, [estimateBuilderCatalog, estimateBuilderExtrasSearch]);

  const shellModals = (
    <>
      <Modal
        visible={menuOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setMenuOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.sectionTitle}>Menu</Text>
            <Text style={styles.subtleText}>Account tools and admin shortcuts.</Text>
            <View style={styles.savedList}>
              <Pressable
                style={styles.smallButton}
                onPress={() => {
                  setMenuOpen(false);
                  openAdminPath('/admin/client_estimates/catereraccount/');
                }}
              >
                <Text style={styles.smallButtonText}>Account / Company Profile</Text>
              </Pressable>
              <Pressable
                style={styles.smallButton}
                onPress={() => {
                  setMenuOpen(false);
                  openAdminPath('/admin/auth/user/');
                }}
              >
                <Text style={styles.smallButtonText}>Delete Account (Admin)</Text>
              </Pressable>
              <Pressable
                style={styles.smallButton}
                onPress={() => {
                  setMenuOpen(false);
                  openAdminPath('/admin/client_estimates/menucategory/');
                }}
              >
                <Text style={styles.smallButtonText}>Menu Categories</Text>
              </Pressable>
              <Pressable
                style={styles.smallButton}
                onPress={() => {
                  setMenuOpen(false);
                  openAdminPath('/admin/client_estimates/menuitem/');
                }}
              >
                <Text style={styles.smallButtonText}>Menu Items</Text>
              </Pressable>
              <Pressable
                style={styles.smallButton}
                onPress={() => {
                  setMenuOpen(false);
                  openAdminPath('/admin/client_estimates/extraitem/');
                }}
              >
                <Text style={styles.smallButtonText}>Extra Items</Text>
              </Pressable>
              <Pressable
                style={styles.smallDangerButton}
                onPress={() => {
                  setMenuOpen(false);
                  handleLogout();
                }}
              >
                <Text style={styles.smallDangerButtonText}>Log Out</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal
        visible={estimateComposerOpen}
        animationType="slide"
        onRequestClose={() => setEstimateComposerOpen(false)}
      >
        <SafeAreaView style={styles.screen} edges={['left', 'right', 'bottom']}>
          <KeyboardAvoidingView
            style={styles.flexOne}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          >
            <View style={modalHeaderStyle}>
              <View style={{ flex: 1 }}>
                <Text style={styles.sectionTitle}>Create Estimate</Text>
                <Text style={styles.subtleText}>Mobile quick-create. Full edit remains available in admin.</Text>
              </View>
              <Pressable style={styles.smallButton} onPress={() => setEstimateComposerOpen(false)}>
                <Text style={styles.smallButtonText}>Close</Text>
              </Pressable>
            </View>

            <ScrollView contentContainerStyle={tabbedContentWrapStyle} keyboardShouldPersistTaps="handled">
              {catererChoices.length > 1 ? (
                <View style={styles.sectionCard}>
                  <Text style={styles.savedTitle}>Company Profile</Text>
                  <View style={styles.inlineActions}>
                    {catererChoices.map((choice) => (
                      <Pressable
                        key={`estimate-caterer-${choice.id}`}
                        style={[
                          styles.smallButton,
                          newEstimateCatererId === choice.id && styles.selectedPill,
                        ]}
                        onPress={() => setNewEstimateCatererId(choice.id)}
                      >
                        <Text
                          style={[
                            styles.smallButtonText,
                            newEstimateCatererId === choice.id && styles.selectedPillText,
                          ]}
                        >
                          {choice.name}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}

              <View style={styles.sectionCard}>
                <TextInput
                  style={styles.input}
                  value={newEstimateCustomer}
                  onChangeText={setNewEstimateCustomer}
                  placeholder="Customer name"
                />
                <TextInput
                  style={styles.input}
                  value={newEstimateEventType}
                  onChangeText={setNewEstimateEventType}
                  placeholder="Event type (e.g. Wedding)"
                />
                <TextInput
                  style={styles.input}
                  value={newEstimateDate}
                  onChangeText={setNewEstimateDate}
                  placeholder="Event date (YYYY-MM-DD)"
                />
                <TextInput
                  style={styles.input}
                  value={newEstimateLocation}
                  onChangeText={setNewEstimateLocation}
                  placeholder="Event location"
                />
                <TextInput
                  style={styles.input}
                  value={newEstimateAdults}
                  onChangeText={setNewEstimateAdults}
                  keyboardType="number-pad"
                  placeholder="Adult guests"
                />
                <TextInput
                  style={styles.input}
                  value={newEstimateKids}
                  onChangeText={setNewEstimateKids}
                  keyboardType="number-pad"
                  placeholder="Kids guests"
                />
              </View>
            </ScrollView>

            <View style={styles.plannerEditorFooter}>
              <Pressable
                style={[styles.primaryButton, creatingEstimate && styles.buttonDisabled]}
                onPress={submitEstimateFromMobile}
                disabled={creatingEstimate}
              >
                {creatingEstimate ? (
                  <ActivityIndicator color="#ffffff" />
                ) : (
                  <Text style={styles.primaryButtonText}>Create Estimate</Text>
                )}
              </Pressable>
              <Pressable style={styles.smallButton} onPress={() => setEstimateComposerOpen(false)}>
                <Text style={styles.smallButtonText}>Cancel</Text>
              </Pressable>
            </View>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>

      <Modal
        visible={estimateBuilderOpen}
        animationType="slide"
        onRequestClose={closeEstimateBuilder}
      >
        <SafeAreaView style={styles.screen} edges={['left', 'right', 'bottom']}>
          <KeyboardAvoidingView
            style={styles.flexOne}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          >
            <View style={modalHeaderStyle}>
              <View style={{ flex: 1 }}>
                <Text style={styles.sectionTitle}>Estimate Builder</Text>
                <Text style={styles.subtleText}>
                  Full mobile estimate flow synced with admin.
                </Text>
              </View>
              <Pressable style={styles.smallButton} onPress={closeEstimateBuilder}>
                <Text style={styles.smallButtonText}>Close</Text>
              </Pressable>
            </View>

            {estimateBuilderLoading ? (
              <View style={styles.screenCenter}>
                <ActivityIndicator size="large" color="#0f766e" />
              </View>
            ) : estimateBuilderEstimate && estimateBuilderCatalog ? (
              <>
                <ScrollView
                  contentContainerStyle={tabbedContentWrapStyle}
                  keyboardShouldPersistTaps="always"
                  keyboardDismissMode="on-drag"
                >
                  <View style={styles.sectionCard}>
                    <View style={styles.builderEstimateHeaderRow}>
                      <View
                        style={[
                          styles.builderEstimateHeaderMain,
                          estimateBuilderHasMultiMealPrices && styles.builderEstimateHeaderMainMulti,
                        ]}
                      >
                        <Text style={styles.savedTitle}>{estimateBuilderEstimate.job_name}</Text>
                        <Text style={styles.subtleText}>
                          #{estimateBuilderEstimate.estimate_number ?? estimateBuilderEstimate.id} •{' '}
                          {estimateBuilderEstimate.caterer_name}
                        </Text>
                      </View>
                      <View
                        style={[
                          styles.builderEstimatePriceGrid,
                          estimateBuilderHasMultiMealPrices && styles.builderEstimatePriceGridMulti,
                        ]}
                      >
                        {estimateBuilderHeaderMealPriceCardRows.map((cardRow, rowIndex) => (
                          <View
                            key={`estimate-builder-meal-price-row-${rowIndex + 1}`}
                            style={styles.builderEstimatePriceRow}
                          >
                            {cardRow.map((row) => (
                              <View
                                key={`estimate-builder-meal-price-${normalizeEstimateMealKey(row.mealName)}`}
                                style={[
                                  styles.builderEstimatePriceCard,
                                  estimateBuilderHasMultiMealPrices && styles.builderEstimatePriceCardMulti,
                                ]}
                              >
                                {estimateBuilderHasMultiMealPrices ? (
                                  <Text
                                    numberOfLines={1}
                                    ellipsizeMode="tail"
                                    style={styles.builderEstimatePriceMealName}
                                  >
                                    {row.mealName}
                                  </Text>
                                ) : null}
                                <Text style={styles.builderEstimatePriceLabel}>Price / guest</Text>
                                <Text style={styles.builderEstimatePriceValue}>
                                  {row.pricePerGuest ? `${SHEKEL_SYMBOL}${row.pricePerGuest}` : '--'}
                                </Text>
                              </View>
                            ))}
                            {estimateBuilderHasMultiMealPrices && cardRow.length === 1 ? (
                              <View style={styles.builderEstimatePriceCardSpacer} />
                            ) : null}
                          </View>
                        ))}
                      </View>
                    </View>
                    {!estimateBuilderEstimate.can_edit ? (
                      <Text style={styles.subtleText}>
                        View-only access. You can print but cannot edit.
                      </Text>
                    ) : null}
                    <View style={styles.inlineActions}>
                      {([
                        ['customer', 'Customer'],
                        ['menu', 'Menu'],
                        ['decor', 'Decor/Rentals'],
                        ['addons', 'Add-ons'],
                        ['summary', 'Summary'],
                        ['additional', 'Additional'],
                      ] as Array<[EstimateBuilderStep, string]>).map(([stepCode, stepLabel]) => (
                        <Pressable
                          key={`builder-step-${stepCode}`}
                          style={[
                            styles.smallButton,
                            estimateBuilderStep === stepCode && styles.selectedPill,
                          ]}
                          onPress={() => setEstimateBuilderStep(stepCode)}
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderStep === stepCode && styles.selectedPillText,
                            ]}
                          >
                            {stepLabel}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>

                  {estimateBuilderStep === 'customer' ? (
                    <View style={styles.sectionCard}>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.customer_name}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  customer_name: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Customer name"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.customer_phone}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  customer_phone: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Customer phone"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.customer_email}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  customer_email: value,
                                }
                              : prev,
                          )
                        }
                        autoCapitalize="none"
                        placeholder="Customer email"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.event_type}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  event_type: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Event type"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.event_date}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  event_date: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Event date (YYYY-MM-DD)"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.event_location}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  event_location: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Event location"
                      />
                      <TextInput
                        style={styles.input}
                        value={String(estimateBuilderEstimate.guest_count ?? '')}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  guest_count: Number.parseInt(value || '0', 10) || 0,
                                }
                              : prev,
                          )
                        }
                        keyboardType="number-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Adult guests"
                      />
                      <TextInput
                        style={styles.input}
                        value={String(estimateBuilderEstimate.guest_count_kids ?? '')}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  guest_count_kids: Number.parseInt(value || '0', 10) || 0,
                                }
                              : prev,
                          )
                        }
                        keyboardType="number-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Kids guests"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.kids_discount_percentage}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  kids_discount_percentage: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Kids discount %"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.exchange_rate}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  exchange_rate: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Exchange rate"
                      />
                      <View style={styles.inlineActions}>
                        {estimateBuilderCatalog.currencies.map((row) => (
                          <Pressable
                            key={`builder-currency-${row.code}`}
                            style={[
                              styles.smallButton,
                              estimateBuilderEstimate.currency === row.code && styles.selectedPill,
                            ]}
                            onPress={() =>
                              setEstimateBuilderEstimate((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      currency: row.code,
                                    }
                                  : prev,
                              )
                            }
                          >
                            <Text
                              style={[
                                styles.smallButtonText,
                                estimateBuilderEstimate.currency === row.code &&
                                  styles.selectedPillText,
                              ]}
                            >
                              {row.code}
                            </Text>
                          </Pressable>
                        ))}
                      </View>
                    </View>
                  ) : null}

                  {estimateBuilderStep === 'menu' ? (
                    <View style={styles.sectionCard}>
                      <Text style={styles.savedTitle}>Meal Plan</Text>
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderMealPlanInput}
                        onChangeText={setEstimateBuilderMealPlanInput}
                        placeholder="One meal per line"
                        multiline
                      />
                      <View style={styles.inlineActions}>
                        {estimateBuilderMealPlan.map((mealName) => (
                          <Pressable
                            key={`builder-meal-${mealName}`}
                            style={[
                              styles.smallButton,
                              activeEstimateBuilderMeal.toLowerCase() === mealName.toLowerCase() &&
                                styles.selectedPill,
                            ]}
                            onPress={() => setEstimateBuilderActiveMeal(mealName)}
                          >
                            <Text
                              style={[
                                styles.smallButtonText,
                                activeEstimateBuilderMeal.toLowerCase() === mealName.toLowerCase() &&
                                  styles.selectedPillText,
                              ]}
                            >
                              {mealName}
                            </Text>
                          </Pressable>
                        ))}
                      </View>
                      <View style={styles.builderMealOverrideCard}>
                        <Text style={styles.savedTitle}>{activeEstimateBuilderMeal} Overrides</Text>
                        <Text style={styles.subtleText}>
                          {activeEstimateBuilderMealEffectivePricePerGuest
                            ? `${SHEKEL_SYMBOL}${activeEstimateBuilderMealEffectivePricePerGuest} / guest • ${activeEstimateBuilderMealEffectiveAdults} adults${activeEstimateBuilderMealEffectiveKids ? ` / ${activeEstimateBuilderMealEffectiveKids} kids` : ''}`
                            : `${activeEstimateBuilderMealEffectiveAdults} adults${activeEstimateBuilderMealEffectiveKids ? ` / ${activeEstimateBuilderMealEffectiveKids} kids` : ''}`}
                        </Text>
                        <View style={styles.builderMealOverrideRow}>
                          <TextInput
                            style={[styles.input, styles.builderMealOverrideInput]}
                            value={activeEstimateBuilderMealDraft.override_price}
                            onChangeText={(value) =>
                              updateEstimateBuilderMealOverrideDraft(
                                activeEstimateBuilderMeal,
                                'override_price',
                                value,
                              )
                            }
                            keyboardType="decimal-pad"
                            inputAccessoryViewID={
                              Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                            }
                            placeholder="Override per guest"
                          />
                          <Pressable
                            style={styles.smallButton}
                            onPress={applyEstimateBuilderMealPriceOverride}
                          >
                            <Text style={styles.smallButtonText}>Apply</Text>
                          </Pressable>
                        </View>
                        <View style={styles.builderMealOverrideRow}>
                          <TextInput
                            style={[styles.input, styles.builderMealGuestInput]}
                            value={activeEstimateBuilderMealDraft.adults}
                            onChangeText={(value) =>
                              updateEstimateBuilderMealOverrideDraft(
                                activeEstimateBuilderMeal,
                                'adults',
                                value,
                              )
                            }
                            keyboardType="number-pad"
                            inputAccessoryViewID={
                              Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                            }
                            placeholder={`Adults (${activeEstimateBuilderMealDefaultAdults})`}
                          />
                          <TextInput
                            style={[styles.input, styles.builderMealGuestInput]}
                            value={activeEstimateBuilderMealDraft.kids}
                            onChangeText={(value) =>
                              updateEstimateBuilderMealOverrideDraft(
                                activeEstimateBuilderMeal,
                                'kids',
                                value,
                              )
                            }
                            keyboardType="number-pad"
                            inputAccessoryViewID={
                              Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                            }
                            placeholder={`Kids (${activeEstimateBuilderMealDefaultKids})`}
                          />
                          <Pressable
                            style={styles.smallButton}
                            onPress={applyEstimateBuilderMealGuestOverride}
                          >
                            <Text style={styles.smallButtonText}>Set guests</Text>
                          </Pressable>
                        </View>
                      </View>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderMenuSearch}
                        onChangeText={setEstimateBuilderMenuSearch}
                        placeholder="Search menu items..."
                      />
                      {filteredEstimateBuilderMenuCategories.map((category) => (
                        <View key={`builder-menu-category-${category.id ?? category.name}`} style={styles.savedCard}>
                          <Text style={styles.savedTitle}>{category.name}</Text>
                          {category.items.map((item) => {
                            const choice = estimateBuilderMenuChoiceMap.get(
                              `${item.id}|${activeEstimateBuilderMeal.toLowerCase()}`,
                            );
                            return (
                              <View key={`builder-menu-item-${item.id}`} style={styles.builderOptionRow}>
                                <View style={styles.builderOptionBody}>
                                  <Text style={styles.savedTitle}>{item.name}</Text>
                                  <Text style={styles.subtleText}>
                                    {SHEKEL_SYMBOL}
                                    {item.price_per_serving} per serving
                                  </Text>
                                  {choice ? (
                                    <TextInput
                                      style={styles.input}
                                      value={choice.notes}
                                      onChangeText={(value) =>
                                        updateEstimateBuilderMenuChoice(item.id, 'notes', value)
                                      }
                                      placeholder="Notes (optional)"
                                    />
                                  ) : null}
                                </View>
                                <Pressable
                                  style={[styles.smallButton, choice && styles.selectedPill]}
                                  onPress={() => toggleEstimateBuilderMenuItem(item)}
                                >
                                  <Text
                                    style={[
                                      styles.smallButtonText,
                                      choice && styles.selectedPillText,
                                    ]}
                                  >
                                    {choice ? 'Remove' : 'Add'}
                                  </Text>
                                </Pressable>
                              </View>
                            );
                          })}
                        </View>
                      ))}
                    </View>
                  ) : null}

                  {estimateBuilderStep === 'decor' || estimateBuilderStep === 'addons' ? (
                    <View style={styles.sectionCard}>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderExtrasSearch}
                        onChangeText={setEstimateBuilderExtrasSearch}
                        placeholder="Search extras..."
                      />
                      {(estimateBuilderStep === 'decor'
                        ? filteredEstimateBuilderDecorCategories
                        : filteredEstimateBuilderAddonCategories
                      ).map((category) => (
                        <View key={`builder-extra-category-${category.code}`} style={styles.savedCard}>
                          <Text style={styles.savedTitle}>{category.label}</Text>
                          {category.items.map((item) => {
                            const line = estimateBuilderExtraLineMap.get(item.id);
                            return (
                              <View key={`builder-extra-item-${item.id}`} style={styles.builderOptionRow}>
                                <View style={styles.builderOptionBody}>
                                  <Text style={styles.savedTitle}>{item.name}</Text>
                                  <Text style={styles.subtleText}>
                                    {SHEKEL_SYMBOL}
                                    {item.price} • {item.charge_type_label}
                                  </Text>
                                  {line ? (
                                    <>
                                      <TextInput
                                        style={styles.input}
                                        value={line.quantity}
                                        onChangeText={(value) =>
                                          updateEstimateBuilderExtraLine(item.id, 'quantity', value)
                                        }
                                        keyboardType="decimal-pad"
                                        inputAccessoryViewID={
                                          Platform.OS === 'ios'
                                            ? NUMERIC_INPUT_ACCESSORY_ID
                                            : undefined
                                        }
                                        placeholder="Quantity"
                                      />
                                      <TextInput
                                        style={styles.input}
                                        value={line.override_price}
                                        onChangeText={(value) =>
                                          updateEstimateBuilderExtraLine(
                                            item.id,
                                            'override_price',
                                            value,
                                          )
                                        }
                                        keyboardType="decimal-pad"
                                        inputAccessoryViewID={
                                          Platform.OS === 'ios'
                                            ? NUMERIC_INPUT_ACCESSORY_ID
                                            : undefined
                                        }
                                        placeholder="Override price (optional)"
                                      />
                                      <TextInput
                                        style={styles.input}
                                        value={line.notes}
                                        onChangeText={(value) =>
                                          updateEstimateBuilderExtraLine(item.id, 'notes', value)
                                        }
                                        placeholder="Notes (optional)"
                                      />
                                    </>
                                  ) : null}
                                </View>
                                <Pressable
                                  style={[styles.smallButton, line && styles.selectedPill]}
                                  onPress={() => toggleEstimateBuilderExtraItem(item)}
                                >
                                  <Text
                                    style={[
                                      styles.smallButtonText,
                                      line && styles.selectedPillText,
                                    ]}
                                  >
                                    {line ? 'Remove' : 'Add'}
                                  </Text>
                                </Pressable>
                              </View>
                            );
                          })}
                        </View>
                      ))}
                    </View>
                  ) : null}

                  {estimateBuilderStep === 'summary' ? (
                    <View style={styles.sectionCard}>
                      <View style={styles.inlineActions}>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.is_ala_carte && styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    is_ala_carte: !prev.is_ala_carte,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.is_ala_carte && styles.selectedPillText,
                            ]}
                          >
                            A la carte
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.wants_real_dishes && styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    wants_real_dishes: !prev.wants_real_dishes,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.wants_real_dishes && styles.selectedPillText,
                            ]}
                          >
                            Real dishes
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.client_tipped_at_event && styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    client_tipped_at_event: !prev.client_tipped_at_event,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.client_tipped_at_event && styles.selectedPillText,
                            ]}
                          >
                            Client tipped at event
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.include_premium_plastic && styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    include_premium_plastic: !prev.include_premium_plastic,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.include_premium_plastic &&
                                styles.selectedPillText,
                            ]}
                          >
                            Premium plastic
                          </Text>
                        </Pressable>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.include_premium_tablecloths &&
                              styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    include_premium_tablecloths: !prev.include_premium_tablecloths,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.include_premium_tablecloths &&
                                styles.selectedPillText,
                            ]}
                          >
                            Premium tablecloths
                          </Text>
                        </Pressable>
                      </View>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.staff_hours}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  staff_hours: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Staff hours"
                      />
                      <TextInput
                        style={styles.input}
                        value={String(estimateBuilderEstimate.extra_waiters || '')}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  extra_waiters: Number.parseInt(value || '0', 10) || 0,
                                }
                              : prev,
                          )
                        }
                        keyboardType="number-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Extra waiters"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.staff_count_override == null ? '' : String(estimateBuilderEstimate.staff_count_override)}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  staff_count_override: value.trim()
                                    ? Number.parseInt(value, 10) || 0
                                    : null,
                                }
                              : prev,
                          )
                        }
                        keyboardType="number-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Staff count override (optional)"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.staff_hourly_rate}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  staff_hourly_rate: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Staff hourly rate"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.staff_tip_per_waiter}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  staff_tip_per_waiter: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Suggested tip per waiter"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.real_dishes_price_per_person}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  real_dishes_price_per_person: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Real dishes price per person"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.real_dishes_flat_fee}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  real_dishes_flat_fee: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Real dishes delivery fee"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.deposit_percentage}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  deposit_percentage: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Deposit %"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.deposit_received}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  deposit_received: value,
                                }
                              : prev,
                          )
                        }
                        keyboardType="decimal-pad"
                        inputAccessoryViewID={
                          Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                        }
                        placeholder="Deposit received"
                      />
                      <View style={styles.savedCard}>
                        <Text style={styles.savedTitle}>Totals</Text>
                        <Text style={styles.subtleText}>
                          Waiters: {estimateBuilderEstimate.summary.waiter_count}
                        </Text>
                        <Text style={styles.subtleText}>
                          Food: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.food_total}
                        </Text>
                        <Text style={styles.subtleText}>
                          Extras: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.extras_total}
                        </Text>
                        <Text style={styles.subtleText}>
                          Staff: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.staff_total}
                        </Text>
                        <Text style={styles.subtleText}>
                          Dishes: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.dishes_total}
                        </Text>
                        <Text style={styles.subtleText}>
                          Grand Total: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.grand_total}
                        </Text>
                        <Text style={styles.subtleText}>
                          Deposit Due: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.deposit_amount}
                        </Text>
                        <Text style={styles.subtleText}>
                          Balance Due: {SHEKEL_SYMBOL}
                          {estimateBuilderEstimate.summary.balance_due}
                        </Text>
                      </View>
                    </View>
                  ) : null}

                  {estimateBuilderStep === 'additional' ? (
                    <View style={styles.sectionCard}>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.plasticware_color}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  plasticware_color: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Chad Paami color"
                      />
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderEstimate.notes_internal}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  notes_internal: value,
                                }
                              : prev,
                          )
                        }
                        multiline
                        placeholder="Internal notes"
                      />
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderEstimate.notes_for_customer}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  notes_for_customer: value,
                                }
                              : prev,
                          )
                        }
                        multiline
                        placeholder="Customer notes"
                      />
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderEstimate.payment_terms}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  payment_terms: value,
                                }
                              : prev,
                          )
                        }
                        multiline
                        placeholder="Payment terms"
                      />
                      <View style={styles.inlineActions}>
                        {estimateBuilderCatalog.payment_methods.map((method) => (
                          <Pressable
                            key={`builder-pay-method-${method.code}`}
                            style={[
                              styles.smallButton,
                              estimateBuilderEstimate.payment_method === method.code &&
                                styles.selectedPill,
                            ]}
                            onPress={() =>
                              setEstimateBuilderEstimate((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      payment_method: method.code,
                                    }
                                  : prev,
                              )
                            }
                          >
                            <Text
                              style={[
                                styles.smallButtonText,
                                estimateBuilderEstimate.payment_method === method.code &&
                                  styles.selectedPillText,
                              ]}
                            >
                              {method.label}
                            </Text>
                          </Pressable>
                        ))}
                      </View>
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderEstimate.payment_instructions}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  payment_instructions: value,
                                }
                              : prev,
                          )
                        }
                        multiline
                        placeholder="Payment instructions"
                      />
                      <TextInput
                        style={[styles.input, styles.noteInput]}
                        value={estimateBuilderEstimate.contract_terms}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  contract_terms: value,
                                }
                              : prev,
                          )
                        }
                        multiline
                        placeholder="Contract terms"
                      />
                      <View style={styles.inlineActions}>
                        <Pressable
                          style={[
                            styles.smallButton,
                            estimateBuilderEstimate.terms_acknowledged && styles.selectedPill,
                          ]}
                          onPress={() =>
                            setEstimateBuilderEstimate((prev) =>
                              prev
                                ? {
                                    ...prev,
                                    terms_acknowledged: !prev.terms_acknowledged,
                                  }
                                : prev,
                            )
                          }
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              estimateBuilderEstimate.terms_acknowledged &&
                                styles.selectedPillText,
                            ]}
                          >
                            Terms acknowledged
                          </Text>
                        </Pressable>
                      </View>
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.signature_name}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  signature_name: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Signature name"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.signature_title}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  signature_title: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Signature title"
                      />
                      <TextInput
                        style={styles.input}
                        value={estimateBuilderEstimate.signature_date}
                        onChangeText={(value) =>
                          setEstimateBuilderEstimate((prev) =>
                            prev
                              ? {
                                  ...prev,
                                  signature_date: value,
                                }
                              : prev,
                          )
                        }
                        placeholder="Signature date (YYYY-MM-DD)"
                      />
                    </View>
                  ) : null}
                </ScrollView>
                <View style={[styles.plannerEditorFooter, styles.estimateBuilderFooter]}>
                  <Pressable
                    style={[
                      styles.primaryButton,
                      styles.estimateBuilderSaveButton,
                      (estimateBuilderSaving || !estimateBuilderEstimate.can_edit) && styles.buttonDisabled,
                    ]}
                    onPress={saveEstimateBuilder}
                    disabled={estimateBuilderSaving || !estimateBuilderEstimate.can_edit}
                  >
                    {estimateBuilderSaving ? (
                      <ActivityIndicator color="#ffffff" />
                    ) : (
                      <Text style={styles.primaryButtonText}>Save Estimate</Text>
                    )}
                  </Pressable>
                </View>
              </>
            ) : (
              <View style={styles.screenCenter}>
                <Text style={styles.subtleText}>No estimate selected for builder.</Text>
              </View>
            )}
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
    </>
  );

  if (booting) {
    return (
      <SafeAreaView style={styles.screenCenter}>
        <ActivityIndicator size="large" color="#0f766e" />
        <Text style={styles.subtleText}>Loading saved session...</Text>
        <StatusBar style="dark" />
      </SafeAreaView>
    );
  }

  if (!token) {
    return (
      <SafeAreaView style={styles.screen}>
        <KeyboardAvoidingView
          style={styles.flexOne}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <View style={styles.loginCard}>
            <Text style={styles.appTitle}>X Planner</Text>
            <Text style={styles.subtleText}>Internal expense capture for estimates</Text>

            <Text style={styles.label}>API Base URL</Text>
            <TextInput
              style={styles.input}
              value={apiBaseUrl}
              onChangeText={setApiBaseUrl}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="https://www.caterbasepro.com"
            />

            <Text style={styles.label}>Username or Email</Text>
            <TextInput
              style={styles.input}
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="owner@example.com"
            />

            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="Password"
            />

            <Pressable
              style={[styles.primaryButton, loggingIn && styles.buttonDisabled]}
              onPress={handleLogin}
              disabled={loggingIn}
            >
              {loggingIn ? (
                <ActivityIndicator color="#ffffff" />
              ) : (
                <Text style={styles.primaryButtonText}>Log In</Text>
              )}
            </Pressable>
          </View>
        </KeyboardAvoidingView>
        <StatusBar style="dark" />
      </SafeAreaView>
    );
  }

  if (!selectedEstimate || (mainTab !== 'expenses' && mainTab !== 'staff')) {
    return (
      <GestureHandlerRootView style={styles.flexOne}>
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={styles.appHeader}>
          <View style={styles.appHeaderLeft}>
            {showBackChevron ? (
              <Pressable style={styles.headerIconButton} onPress={handleBackChevron}>
                <Text style={styles.headerIconGlyph}>‹</Text>
              </Pressable>
            ) : null}
            <View style={styles.appHeaderTitleWrap}>
              <Text style={styles.appHeaderTitle}>
                {mainTab === 'estimates'
                  ? 'Estimates'
                  : mainTab === 'shopping'
                    ? selectedShoppingList
                      ? selectedShoppingList.title
                      : 'Shopping'
                    : mainTab === 'planner'
                      ? selectedPlannerEstimate
                        ? plannerSection
                          ? activePlannerSectionConfig?.label || 'Planner'
                          : `${selectedPlannerEstimate.job_name} Planner`
                        : 'Planner'
                      : mainTab === 'staff'
                        ? 'Staff'
                        : 'Expenses'}
              </Text>
              <Text style={styles.appHeaderSubtitle}>
                {mainTab === 'shopping'
                  ? 'Live list updates'
                  : mainTab === 'planner'
                    ? 'Planning board'
                    : mainTab === 'estimates'
                      ? 'Build and manage jobs'
                      : 'Job workspace'}
              </Text>
            </View>
          </View>
          <View style={styles.appHeaderRight}>
            <Pressable
              style={styles.headerIconButton}
              onPress={() => {
                if (mainTab === 'estimates' || mainTab === 'expenses' || mainTab === 'staff') {
                  loadEstimates();
                  return;
                }
                if (mainTab === 'shopping' && selectedShoppingList) {
                  Promise.all([
                    loadShoppingListDetail(selectedShoppingList.id),
                    loadShoppingCatalog(),
                  ]);
                  return;
                }
                if (mainTab === 'shopping') {
                  Promise.all([loadShoppingLists(), loadShoppingCatalog()]);
                  return;
                }
                if (selectedPlannerEstimate) {
                  loadPlannerData(selectedPlannerEstimate.id);
                } else {
                  loadEstimates();
                }
              }}
            >
              <RefreshCcw size={18} color="#64748b" />
            </Pressable>
            <Pressable style={styles.headerIconButton} onPress={() => setMenuOpen(true)}>
              <CircleEllipsis size={18} color="#64748b" />
            </Pressable>
          </View>
        </View>

        <View style={styles.flexOne}>
          {mainTab === 'estimates' || mainTab === 'expenses' || mainTab === 'staff' ? (
          loadingJobs ? (
            <View style={styles.screenCenter}>
              <ActivityIndicator size="large" color="#0f766e" />
            </View>
          ) : (
            <ScrollView contentContainerStyle={tabbedJobsListWrapStyle}>
              {mainTab === 'estimates' ? (
                <View style={styles.sectionCard}>
                  <Text style={styles.subtleText}>
                    Create a new estimate from mobile, then manage expenses, staff, shopping, and planner.
                  </Text>
                  <Pressable
                    style={styles.primaryButton}
                    onPress={() => {
                      if (!newEstimateCatererId && catererChoices.length) {
                        setNewEstimateCatererId(catererChoices[0].id);
                      }
                      setEstimateComposerOpen(true);
                    }}
                  >
                    <Text style={styles.primaryButtonText}>+ New Estimate</Text>
                  </Pressable>
                </View>
              ) : (
                <Text style={styles.subtleText}>
                  Select an estimate to open the {mainTab === 'staff' ? 'staff' : 'expense'} workspace.
                </Text>
              )}
              {estimates.map((estimate) => (
                <Pressable
                  key={estimate.id}
                  style={styles.jobCard}
                  onPress={() => {
                    if (mainTab === 'estimates') {
                      openEstimateBuilder(estimate);
                      return;
                    }
                    handleSelectEstimate(
                      estimate,
                      mainTab === 'staff' ? 'staff' : 'expenses',
                    );
                  }}
                  onLongPress={() => openEstimatePrintOptions(estimate)}
                >
                  <Text style={styles.jobTitle}>{estimate.job_name}</Text>
                  <Text style={styles.subtleText}>
                    #{estimate.estimate_number ?? 'N/A'} • {formatDate(estimate.event_date)}
                  </Text>
                  <Text style={styles.subtleText}>
                    {estimate.can_view_billing
                      ? `${estimate.currency} ${estimate.grand_total} • ${estimate.expense_count} saved entries`
                      : `${estimate.expense_count} saved entries`}
                  </Text>
                  <View style={styles.inlineActions}>
                    {mainTab === 'estimates' ? (
                      <Pressable style={styles.smallButton} onPress={() => openEstimateBuilder(estimate)}>
                        <Text style={styles.smallButtonText}>Builder</Text>
                      </Pressable>
                    ) : null}
                    <Pressable style={styles.smallButton} onPress={() => openEstimatePrintOptions(estimate)}>
                      <Text style={styles.smallButtonText}>Print</Text>
                    </Pressable>
                    {mainTab === 'estimates' ? (
                      <>
                        <Pressable
                          style={styles.smallButton}
                          onPress={() => handleSelectEstimate(estimate, 'expenses')}
                        >
                          <Text style={styles.smallButtonText}>Expenses</Text>
                        </Pressable>
                        <Pressable
                          style={styles.smallButton}
                          onPress={() => handleSelectEstimate(estimate, 'staff')}
                        >
                          <Text style={styles.smallButtonText}>Staff</Text>
                        </Pressable>
                      </>
                    ) : null}
                    {mainTab === 'expenses' ? (
                      <Pressable
                        style={styles.smallButton}
                        onPress={() => handleSelectEstimate(estimate, 'expenses')}
                      >
                        <Text style={styles.smallButtonText}>Expenses</Text>
                      </Pressable>
                    ) : null}
                    {mainTab === 'staff' ? (
                      <Pressable
                        style={styles.smallButton}
                        onPress={() => handleSelectEstimate(estimate, 'staff')}
                      >
                        <Text style={styles.smallButtonText}>Staff</Text>
                      </Pressable>
                    ) : null}
                  </View>
                </Pressable>
              ))}
              {!estimates.length && <Text style={styles.subtleText}>No estimates found for this account.</Text>}
            </ScrollView>
          )
        ) : mainTab === 'shopping' ? (
          selectedShoppingList ? (
            <ScrollView
              contentContainerStyle={tabbedNativeContentWrapStyle}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
                <View style={styles.nativeContentInner}>
                  <View style={styles.nativeScreenHeader}>
                    <Text style={styles.nativeScreenTitle} numberOfLines={1}>
                      {selectedShoppingList.title}
                    </Text>
                    <Text style={styles.nativeScreenSubtitle}>
                      {selectedShoppingList.estimate_label
                        ? `${selectedShoppingList.caterer_name} • ${selectedShoppingList.estimate_label}`
                        : selectedShoppingList.caterer_name}
                    </Text>
                    <View style={styles.nativeHeaderActions}>
                      <Pressable
                        style={styles.headerIconButton}
                        onPress={() =>
                          Promise.all([
                            loadShoppingListDetail(selectedShoppingList.id),
                            loadShoppingCatalog(),
                          ])
                        }
                      >
                        <RefreshCcw size={18} color="#64748b" />
                      </Pressable>
                      <Pressable
                        style={styles.headerTextButton}
                        onPress={() =>
                          setShoppingListScreenMode((prev) => (prev === 'manage' ? 'list' : 'manage'))
                        }
                      >
                        <Text style={styles.headerTextButtonLabel}>
                          {shoppingListScreenMode === 'manage' ? 'View list' : 'Manage'}
                        </Text>
                      </Pressable>
                      <Pressable
                        style={styles.headerTextButton}
                        onPress={() => {
                          setSelectedShoppingList(null);
                          setShoppingItems([]);
                          setSavedItemSearchText('');
                          setSavedItemExpandedKey(null);
                          setSavedItemQuickUnitPickerOpen(false);
                          setShoppingListScreenMode('manage');
                        }}
                      >
                        <Text style={styles.headerTextButtonLabel}>Lists</Text>
                      </Pressable>
                    </View>
                  </View>

                  {shoppingListScreenMode === 'manage' ? (
                    <View style={styles.nativeFormGroup}>
                      <View style={styles.nativeRowBetween}>
                        <Text style={styles.nativeSectionHeading}>Saved Items</Text>
                        <Pressable style={styles.headerTextButton} onPress={() => loadShoppingCatalog()}>
                          <Text style={styles.headerTextButtonLabel}>Refresh</Text>
                        </Pressable>
                      </View>
                      <TextInput
                        ref={savedItemSearchInputRef}
                        style={styles.nativeInput}
                        value={savedItemSearchText}
                        onChangeText={(value) => {
                          setSavedItemSearchText(value);
                          setSavedItemExpandedKey(null);
                          setSavedItemQuickUnitPickerOpen(false);
                        }}
                        placeholder="Add item..."
                        autoCorrect={false}
                        autoCapitalize="none"
                        returnKeyType="search"
                      />
                      {!!savedItemSearchText.trim() ? (
                        <Text style={styles.subtleText}>
                          Search results update instantly as you type.
                        </Text>
                      ) : (
                        <Text style={styles.subtleText}>
                          Search, tap an item, adjust qty, then add in one step.
                        </Text>
                      )}
                    </View>
                  ) : null}

                  {shoppingListScreenMode === 'manage' && !!savedItemSearchText.trim() ? (
                    <View style={styles.nativeFormGroup}>
                      <View style={styles.nativeSectionBlock}>
                        <Text style={styles.nativeSectionHeading}>RESULTS</Text>
                        <View style={styles.nativeListSurface}>
                          {filteredSavedItems.map((item, index) => {
                            const itemKey = item.item_name.trim().toLowerCase();
                            return (
                              <View key={`result-top-${itemKey}`} style={index > 0 ? styles.nativeListDivider : undefined}>
                                <NativeListItem
                                  title={item.item_name}
                                  subtitle={
                                    item.last_used_unit
                                      ? `Default unit: ${item.last_used_unit}`
                                      : 'Default unit: none'
                                  }
                                  onPress={() => openSavedItemQuickAdd(item)}
                                  rightSlot={<Plus size={16} color="#64748b" />}
                                />
                                {renderSavedItemQuickAddRow(item, itemKey)}
                              </View>
                            );
                          })}
                          {!filteredSavedItems.length && !hasExactSavedItemMatch ? (
                            <>
                              <NativeListItem
                                title={`Create "${savedItemSearchText.trim()}"`}
                                subtitle="New item with quick defaults"
                                onPress={openCustomSavedItemQuickAdd}
                                rightSlot={<Plus size={16} color="#64748b" />}
                              />
                              {renderSavedItemQuickAddRow(null, '__new__')}
                            </>
                          ) : null}
                          {!filteredSavedItems.length && hasExactSavedItemMatch ? (
                            <Text style={styles.subtleText}>No saved items match this search.</Text>
                          ) : null}
                        </View>
                      </View>
                    </View>
                  ) : null}

                  {loadingShoppingItems ? (
                    <View style={styles.nativeListLoading}>
                      <ActivityIndicator color="#0f766e" />
                    </View>
                  ) : (
                    <View style={styles.nativeListGroupWrap}>
                      {shoppingSections.map((section) => (
                        <View key={section.label} style={styles.nativeSectionBlock}>
                          <Text style={styles.nativeSectionHeading}>{section.label.toUpperCase()}</Text>
                          <View style={styles.nativeListSurface}>
                            {section.items.map((item, index) => (
                              <Swipeable
                                key={item.id}
                                overshootRight={false}
                                renderRightActions={() => (
                                  <Pressable
                                    style={[
                                      styles.swipeDeleteAction,
                                      removingShoppingItemId === item.id && styles.buttonDisabled,
                                    ]}
                                    onPress={() => handleRemoveShoppingItem(item)}
                                    disabled={removingShoppingItemId === item.id}
                                  >
                                    <Text style={styles.swipeDeleteActionText}>Delete</Text>
                                  </Pressable>
                                )}
                              >
                                <View
                                  style={[
                                    index > 0 && styles.nativeListDivider,
                                    removingShoppingItemId === item.id && styles.buttonDisabled,
                                  ]}
                                >
                                  <NativeListItem
                                    title={item.item_name}
                                    subtitle={`Qty ${item.quantity}${item.item_unit ? ` ${item.item_unit}` : ''}${
                                      item.item_type ? ` • ${item.item_type}` : ''
                                    }`}
                                    meta={item.collaboration_note || undefined}
                                    rightSlot={
                                      <View style={styles.shoppingRowActions}>
                                        {shoppingListScreenMode === 'manage' ? (
                                          <Pressable
                                            style={styles.shoppingRowEditButton}
                                            onPress={(event) => {
                                              event.stopPropagation();
                                              openShoppingItemEditor(item);
                                            }}
                                          >
                                            <Text style={styles.shoppingRowEditButtonText}>Edit</Text>
                                          </Pressable>
                                        ) : null}
                                        <Pressable
                                          style={[
                                            styles.shoppingRowDeleteButton,
                                            removingShoppingItemId === item.id && styles.buttonDisabled,
                                          ]}
                                          onPress={(event) => {
                                            event.stopPropagation();
                                            handleRemoveShoppingItem(item);
                                          }}
                                          disabled={removingShoppingItemId === item.id}
                                        >
                                          <Text style={styles.shoppingRowDeleteButtonText}>
                                            {removingShoppingItemId === item.id ? '…' : '✕'}
                                          </Text>
                                        </Pressable>
                                      </View>
                                    }
                                  />
                                </View>
                              </Swipeable>
                            ))}
                          </View>
                        </View>
                      ))}
                      {!shoppingItems.length ? (
                        <Text style={styles.subtleText}>No items yet. Add the first item above.</Text>
                      ) : null}
                    </View>
                  )}

                  {shoppingListScreenMode === 'manage' ? (
                    <View style={styles.nativeFormGroup}>
                      {loadingShoppingCatalog ? (
                        <ActivityIndicator color="#0f766e" />
                      ) : (
                        <>
                          {recentSavedItems.length ? (
                            <View style={styles.nativeSectionBlock}>
                              <Text style={styles.nativeSectionHeading}>RECENT</Text>
                              <View style={styles.nativeListSurface}>
                                {recentSavedItems.map((item, index) => {
                                  const itemKey = item.item_name.trim().toLowerCase();
                                  return (
                                    <View key={`recent-${itemKey}`} style={index > 0 ? styles.nativeListDivider : undefined}>
                                      <NativeListItem
                                        title={item.item_name}
                                        subtitle={
                                          item.last_used_unit
                                            ? `Default unit: ${item.last_used_unit}`
                                            : 'Default unit: none'
                                        }
                                        onPress={() => openSavedItemQuickAdd(item)}
                                        rightSlot={<Plus size={16} color="#64748b" />}
                                      />
                                      {renderSavedItemQuickAddRow(item, itemKey)}
                                    </View>
                                  );
                                })}
                              </View>
                            </View>
                          ) : null}

                          {frequentSavedItems.length ? (
                            <View style={styles.nativeSectionBlock}>
                              <Text style={styles.nativeSectionHeading}>FREQUENT</Text>
                              <View style={styles.savedQuickChipsWrap}>
                                {frequentSavedItems.map((item) => (
                                  <Pressable
                                    key={`freq-${item.item_name}`}
                                    style={styles.savedQuickItemChip}
                                    onPress={() => openSavedItemQuickAdd(item)}
                                  >
                                    <Text style={styles.savedQuickItemChipText}>{item.item_name}</Text>
                                  </Pressable>
                                ))}
                              </View>
                              {frequentExpandedItem && !expandedItemInRecent
                                ? renderSavedItemQuickAddRow(
                                    frequentExpandedItem,
                                    frequentExpandedItem.item_name.trim().toLowerCase(),
                                  )
                                : null}
                            </View>
                          ) : null}

                          <View style={styles.nativeSectionBlock}>
                            <Text style={styles.nativeSectionHeading}>CATEGORIES</Text>
                            {shoppingCatalogCategories.map((category) => (
                              <View key={category.category} style={styles.nativeSectionBlock}>
                                <Pressable
                                  style={styles.nativeCategoryToggle}
                                  onPress={() =>
                                    setOpenCatalogCategory((prev) =>
                                      prev === category.category ? null : category.category,
                                    )
                                  }
                                >
                                  <Text style={styles.nativeSectionHeading}>
                                    {category.category_label.toUpperCase()}
                                  </Text>
                                  <ChevronRight
                                    size={16}
                                    color="#94a3b8"
                                    style={[
                                      styles.nativeCategoryChevron,
                                      openCatalogCategory === category.category &&
                                        styles.nativeCategoryChevronOpen,
                                    ]}
                                  />
                                </Pressable>
                                {openCatalogCategory === category.category ? (
                                  <View style={styles.nativeListSurface}>
                                    {category.items.map((item, index) => {
                                      const itemKey = item.item_name.trim().toLowerCase();
                                      const catalogRow: ShoppingCatalogListItem = {
                                        ...item,
                                        category: category.category,
                                        category_label: category.category_label,
                                      };
                                      return (
                                        <View
                                          key={`${category.category}-${item.item_name}`}
                                          style={index > 0 ? styles.nativeListDivider : undefined}
                                        >
                                          <NativeListItem
                                            title={item.item_name}
                                            subtitle={
                                              item.last_used_unit
                                                ? `Default unit: ${item.last_used_unit}`
                                                : 'Default unit: none'
                                            }
                                            onPress={() => openSavedItemQuickAdd(catalogRow)}
                                            rightSlot={<Plus size={16} color="#64748b" />}
                                          />
                                          {renderSavedItemQuickAddRow(catalogRow, itemKey)}
                                        </View>
                                      );
                                    })}
                                  </View>
                                ) : null}
                              </View>
                            ))}
                            {!shoppingCatalogCategories.length ? (
                              <Text style={styles.subtleText}>
                                No saved items yet. Add a new item name from search.
                              </Text>
                            ) : null}
                          </View>
                        </>
                      )}
                    </View>
                  ) : null}
                </View>
              </TouchableWithoutFeedback>
            </ScrollView>
          ) : (
            <ScrollView
              contentContainerStyle={tabbedNativeContentWrapStyle}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <View style={styles.nativeContentInner}>
                <View style={styles.nativeScreenHeader}>
                  <Text style={styles.nativeScreenTitle}>Shopping Lists</Text>
                  <Text style={styles.nativeScreenSubtitle}>
                    Create and open live shared shopping checklists.
                  </Text>
                </View>
                <View style={styles.nativeFormGroup}>
                  <Text style={styles.nativeSectionHeading}>Create List</Text>
                  <TextInput
                    style={styles.nativeInput}
                    value={shoppingListTitle}
                    onChangeText={setShoppingListTitle}
                    placeholder="List title"
                  />
                  {catererChoices.length > 1 && !shoppingEstimateRefId ? (
                    <ScrollView
                      horizontal
                      showsHorizontalScrollIndicator={false}
                      contentContainerStyle={styles.nativeChipRow}
                    >
                      {catererChoices.map((choice) => (
                        <Pressable
                          key={choice.id}
                          style={[
                            styles.nativeChip,
                            shoppingCatererId === choice.id && styles.nativeChipSelected,
                          ]}
                          onPress={() => setShoppingCatererId(choice.id)}
                        >
                          <Text
                            style={[
                              styles.nativeChipLabel,
                              shoppingCatererId === choice.id && styles.nativeChipLabelSelected,
                            ]}
                          >
                            {choice.name}
                          </Text>
                        </Pressable>
                      ))}
                    </ScrollView>
                  ) : null}
                  <View style={styles.nativeRowBetween}>
                    <Pressable style={styles.headerTextButton} onPress={() => setShowEstimatePicker(true)}>
                      <Text style={styles.headerTextButtonLabel}>
                        {selectedEstimateReference
                          ? `Linked: #${selectedEstimateReference.estimate_number ?? selectedEstimateReference.id}`
                          : 'Link job (optional)'}
                      </Text>
                    </Pressable>
                    {selectedEstimateReference ? (
                      <Pressable style={styles.headerTextButton} onPress={() => setShoppingEstimateRefId(null)}>
                        <Text style={styles.headerTextButtonLabel}>Clear</Text>
                      </Pressable>
                    ) : null}
                  </View>
                  <Pressable
                    style={[styles.inlinePrimaryAction, creatingShoppingList && styles.buttonDisabled]}
                    onPress={handleCreateShoppingList}
                    disabled={creatingShoppingList}
                  >
                    {creatingShoppingList ? (
                      <ActivityIndicator color="#ffffff" />
                    ) : (
                      <>
                        <Plus size={16} color="#ffffff" />
                        <Text style={styles.inlinePrimaryActionText}>Create shopping list</Text>
                      </>
                    )}
                  </Pressable>
                </View>
                <View style={styles.nativeSectionBlock}>
                  <View style={styles.nativeRowBetween}>
                    <Text style={styles.nativeSectionHeading}>Your Lists</Text>
                    <Pressable style={styles.headerIconButton} onPress={() => loadShoppingLists()}>
                      <RefreshCcw size={16} color="#64748b" />
                    </Pressable>
                  </View>
                  {loadingShoppingLists ? (
                    <ActivityIndicator color="#0f766e" />
                  ) : (
                    <View style={styles.nativeListSurface}>
                      {shoppingLists.map((row, index) => (
                        <Swipeable
                          key={row.id}
                          overshootRight={false}
                          renderRightActions={() => (
                            <Pressable
                              style={[
                                styles.swipeDeleteAction,
                                deletingShoppingListId === row.id && styles.buttonDisabled,
                              ]}
                              onPress={() => handleDeleteShoppingList(row)}
                              disabled={deletingShoppingListId === row.id}
                            >
                              <Text style={styles.swipeDeleteActionText}>Delete</Text>
                            </Pressable>
                          )}
                        >
                          <View style={index > 0 ? styles.nativeListDivider : undefined}>
                            <NativeListItem
                              title={row.title}
                              subtitle={`${row.item_count} items${row.estimate_label ? ` • ${row.estimate_label}` : ''}`}
                              meta={row.caterer_name}
                              onPress={() => openShoppingList(row)}
                              rightSlot={<ChevronRight size={17} color="#94a3b8" />}
                            />
                          </View>
                        </Swipeable>
                      ))}
                      {!shoppingLists.length ? (
                        <Text style={styles.subtleText}>No shopping lists yet.</Text>
                      ) : null}
                    </View>
                  )}
                </View>
              </View>
            </ScrollView>
          )
        ) : (
          !selectedPlannerEstimate ? (
            loadingJobs ? (
              <View style={styles.screenCenter}>
                <ActivityIndicator size="large" color="#0f766e" />
              </View>
            ) : (
              <ScrollView contentContainerStyle={tabbedJobsListWrapStyle}>
                {estimates.map((estimate) => (
                  <Pressable
                    key={estimate.id}
                    style={styles.jobCard}
                    onPress={() => handleSelectPlannerEstimate(estimate)}
                  >
                    <Text style={styles.jobTitle}>{estimate.job_name}</Text>
                    <Text style={styles.subtleText}>
                      #{estimate.estimate_number ?? 'N/A'} • {formatDate(estimate.event_date)}
                    </Text>
                    <Text style={styles.subtleText}>{estimate.caterer_name}</Text>
                  </Pressable>
                ))}
                {!estimates.length ? (
                  <Text style={styles.subtleText}>No estimates found for this account.</Text>
                ) : null}
              </ScrollView>
            )
          ) : !plannerSection ? (
            <ScrollView contentContainerStyle={tabbedContentWrapStyle}>
              <View style={styles.sectionCard}>
                <View style={styles.listHeaderTopRow}>
                  <Text style={[styles.sectionTitle, styles.listHeaderTitle]} numberOfLines={2}>
                    {selectedPlannerEstimate.job_name}
                  </Text>
                  <Pressable
                    style={styles.smallButton}
                    onPress={() => {
                      setSelectedPlannerEstimate(null);
                      setPlannerSection(null);
                      setPlannerCategoryCode('');
                      setPlannerItemCatalog([]);
                      setPlannerIconOverrides([]);
                      setPlannerFieldCards([]);
                      setPlannerSearchText('');
                      closePlannerEditor();
                    }}
                  >
                    <Text style={styles.smallButtonText}>Back to Jobs</Text>
                  </Pressable>
                </View>
                <Text style={styles.subtleText}>
                  {selectedPlannerEstimate.customer_name} • {formatDate(selectedPlannerEstimate.event_date)}
                </Text>
                <Text style={styles.subtleText}>
                  Pick a planning area. Each entry is saved to this estimate checklist and planning PDF.
                </Text>
                {loadingPlanner ? <ActivityIndicator color="#0f766e" /> : null}
              </View>

              <View style={styles.plannerGrid}>
                {PLANNER_SECTION_CHOICES.map((section) => {
                  const stats = plannerProgressBySection.get(section.code);
                  const total = stats?.total || 0;
                  const completed = stats?.completed || 0;
                  const sectionIcon = PLANNER_SECTION_ICON_MAP[section.icon] || 'circle';
                  return (
                    <Pressable
                      key={section.code}
                      style={styles.plannerIconCard}
                      onPress={() => {
                        setPlannerSection(section.code);
                        setPlannerCategoryCode('');
                        setPlannerSearchText('');
                      }}
                    >
                      <View style={styles.plannerIconBadge}>
                        {renderPlannerIcon(sectionIcon, 28, '#0f766e')}
                      </View>
                      <Text style={styles.plannerIconLabel}>{section.label}</Text>
                      <Text style={styles.plannerIconMeta}>
                        {completed}/{total} checked
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </ScrollView>
          ) : (
            <ScrollView
              contentContainerStyle={tabbedContentWrapStyle}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
                <View style={styles.contentTapDismissArea}>
                  <View style={styles.sectionCard}>
                    <View style={styles.listHeaderTopRow}>
                      <View style={styles.plannerSectionTitleRow}>
                        <View style={styles.plannerSectionGlyph}>
                          {renderPlannerIcon(
                            PLANNER_SECTION_ICON_MAP[activePlannerSectionConfig?.icon || ''] || 'circle',
                            18,
                            '#0f766e',
                          )}
                        </View>
                        <View style={styles.plannerSectionTitleTextWrap}>
                          <Text style={styles.sectionTitle}>
                            {activePlannerSectionConfig?.label || 'Planner'}
                          </Text>
                          {plannerCategoryCode && activePlannerCategory ? (
                            <Text style={styles.subtleText}>{activePlannerCategory.label}</Text>
                          ) : null}
                        </View>
                      </View>
                      <View style={styles.inlineActions}>
                        <Pressable
                          style={styles.smallButton}
                          onPress={() => {
                            if (plannerCategoryCode) {
                              setPlannerCategoryCode('');
                              setPlannerSearchText('');
                              return;
                            }
                            setPlannerSection(null);
                          }}
                        >
                          <Text style={styles.smallButtonText}>
                            {plannerCategoryCode ? 'Categories' : 'Board'}
                          </Text>
                        </Pressable>
                      </View>
                    </View>
                    <TextInput
                      style={styles.input}
                      value={plannerSearchText}
                      onChangeText={setPlannerSearchText}
                      placeholder={
                        plannerCategoryCode ? 'Search options...' : 'Search planner categories...'
                      }
                    />
                    <Text style={styles.subtleText}>
                      {plannerCategoryCode && activePlannerCategory?.itemOptions?.length
                        ? `Options for ${activePlannerCategory.label}. Tap an option to add or edit variables.`
                        : `Checklist view for ${selectedPlannerEstimate.job_name}. Tap a category to add or edit entries.`}
                    </Text>
                    {plannerCategoryCode && activePlannerCategory?.itemOptions?.length ? (
                      <>
                        <View style={styles.plannerAddOptionRow}>
                          <TextInput
                            style={[styles.input, styles.plannerAddOptionInput]}
                            value={plannerNewOptionName}
                            onChangeText={setPlannerNewOptionName}
                            placeholder={`Add new ${activePlannerCategory.label} option`}
                            returnKeyType="done"
                            onSubmitEditing={addPlannerOptionToGroup}
                          />
                          <Pressable
                            style={[styles.smallButton, savingPlanner && styles.buttonDisabled]}
                            onPress={addPlannerOptionToGroup}
                            disabled={savingPlanner}
                          >
                            <Text style={styles.smallButtonText}>
                              {savingPlanner ? 'Adding...' : '+ Add Option'}
                            </Text>
                          </Pressable>
                        </View>
                        <Text style={styles.subtleText}>
                          New option cards are remembered and available on future jobs.
                        </Text>
                      </>
                    ) : null}
                  </View>

                  {plannerCategoryCode && activePlannerCategory?.itemOptions?.length ? (
                    <View style={styles.sectionCard}>
                      <View style={styles.headerRow}>
                        <Text style={styles.sectionTitle}>Options</Text>
                        <Text style={styles.subtleText}>
                          {filteredPlannerOptionCards.filter((card) => card.isAdded).length}/
                          {filteredPlannerOptionCards.length} added
                        </Text>
                      </View>
                      {loadingPlanner ? (
                        <ActivityIndicator color="#0f766e" />
                      ) : (
                        <View style={styles.savedList}>
                          {filteredPlannerOptionCards.map((card) => {
                            const primary = card.entries[0];
                            return (
                              <Pressable
                                key={card.key}
                                style={[
                                  styles.plannerChecklistCard,
                                  !card.isAdded && styles.plannerChecklistCardPending,
                                  card.isAdded && card.isChecked && styles.plannerChecklistCardDone,
                                ]}
                                onPress={() => openPlannerGroupCard(card.groupCode, card.itemCode, primary)}
                              >
                                <View style={styles.plannerChecklistMain}>
                                  <View style={styles.plannerChecklistBody}>
                                    <View style={styles.plannerChecklistTitleRow}>
                                      <View style={styles.plannerChecklistIconBadge}>
                                        {renderPlannerIcon(card.icon, 16, '#0f766e')}
                                      </View>
                                      <View style={styles.plannerChecklistTitleWrap}>
                                        <Text style={styles.plannerChecklistTitle}>{card.label}</Text>
                                        {card.secondaryLabel ? (
                                          <Text style={styles.plannerChecklistSubtitle}>
                                            {card.secondaryLabel}
                                          </Text>
                                        ) : null}
                                      </View>
                                    </View>
                                    {!card.isAdded ? (
                                      <Text style={styles.plannerChecklistMissingText}>Not added yet</Text>
                                    ) : null}
                                    {card.summaryLines.length ? (
                                      <View style={styles.plannerChecklistSummary}>
                                        {card.summaryLines.map((line, index) => (
                                          <Text key={`${card.key}-line-${index}`} style={styles.subtleText}>
                                            {line}
                                          </Text>
                                        ))}
                                      </View>
                                    ) : (
                                      <Text style={styles.plannerChecklistPlaceholder}>
                                        Tap to add this option.
                                      </Text>
                                    )}
                                  </View>
                                </View>
                                {card.isAdded ? (
                                  <View style={styles.inlineActions}>
                                    <Pressable style={styles.smallButton} onPress={() => openPlannerEditor(primary)}>
                                      <Text style={styles.smallButtonText}>Edit</Text>
                                    </Pressable>
                                    {primary ? (
                                      <Pressable
                                        style={styles.smallDangerButton}
                                        onPress={() => deletePlannerEntry(primary)}
                                      >
                                        <Text style={styles.smallDangerButtonText}>Delete</Text>
                                      </Pressable>
                                    ) : null}
                                  </View>
                                ) : null}
                              </Pressable>
                            );
                          })}
                          {!filteredPlannerOptionCards.length ? (
                            <Text style={styles.subtleText}>
                              No options matched your search.
                            </Text>
                          ) : null}
                        </View>
                      )}
                    </View>
                  ) : (
                    <View style={styles.sectionCard}>
                      <View style={styles.headerRow}>
                        <Text style={styles.sectionTitle}>Checklist</Text>
                        <Text style={styles.subtleText}>
                          {
                            filteredPlannerCategoryCards.filter(
                              (card) => card.isAdded && card.isChecked,
                            ).length
                          }/
                          {filteredPlannerCategoryCards.filter((card) => card.isAdded).length} done
                        </Text>
                      </View>
                      {loadingPlanner ? (
                        <ActivityIndicator color="#0f766e" />
                      ) : (
                        <View style={styles.savedList}>
                          {filteredPlannerCategoryCards.map((card) => {
                            const primary = card.entries[0];
                            const hasOptions = !!plannerGroupForActive(plannerSection, card.groupCode)?.itemOptions
                              ?.length;
                            return (
                              <Pressable
                                key={card.key}
                                style={[
                                  styles.plannerChecklistCard,
                                  !card.isAdded && styles.plannerChecklistCardPending,
                                  card.isAdded && card.isChecked && styles.plannerChecklistCardDone,
                                ]}
                                onPress={() => {
                                  if (hasOptions) {
                                    setPlannerCategoryCode(card.groupCode);
                                    setPlannerSearchText('');
                                    return;
                                  }
                                  openPlannerGroupCard(card.groupCode, card.itemCode, primary);
                                }}
                              >
                                <View style={styles.plannerChecklistMain}>
                                  <View style={styles.plannerChecklistBody}>
                                    <View style={styles.plannerChecklistTitleRow}>
                                      <View style={styles.plannerChecklistIconBadge}>
                                        {renderPlannerIcon(card.icon, 16, '#0f766e')}
                                      </View>
                                      <View style={styles.plannerChecklistTitleWrap}>
                                        <Text style={styles.plannerChecklistTitle}>{card.label}</Text>
                                      </View>
                                    </View>
                                    {!card.isAdded ? (
                                      <Text style={styles.plannerChecklistMissingText}>Not added yet</Text>
                                    ) : null}
                                    {card.summaryLines.length ? (
                                      <View style={styles.plannerChecklistSummary}>
                                        {card.summaryLines.map((line, index) => (
                                          <Text key={`${card.key}-line-${index}`} style={styles.subtleText}>
                                            {line}
                                          </Text>
                                        ))}
                                      </View>
                                    ) : (
                                      <Text style={styles.plannerChecklistPlaceholder}>
                                        {hasOptions
                                          ? 'Tap to open this category.'
                                          : 'Tap to add this checklist item.'}
                                      </Text>
                                    )}
                                  </View>
                                  {card.isAdded ? (
                                    hasOptions ? (
                                      <View
                                        style={[
                                          styles.plannerCheckCircle,
                                          card.isChecked && styles.plannerCheckCircleChecked,
                                        ]}
                                      >
                                        <Text
                                          style={[
                                            styles.plannerCheckCircleText,
                                            card.isChecked && styles.plannerCheckCircleTextChecked,
                                          ]}
                                        >
                                          {card.isChecked ? '✓' : ''}
                                        </Text>
                                      </View>
                                    ) : (
                                      <Pressable
                                        style={[
                                          styles.plannerCheckCircle,
                                          card.isChecked && styles.plannerCheckCircleChecked,
                                        ]}
                                        onPress={(event) => {
                                          event.stopPropagation();
                                          if (primary) {
                                            togglePlannerChecked(primary);
                                          }
                                        }}
                                      >
                                        <Text
                                          style={[
                                            styles.plannerCheckCircleText,
                                            card.isChecked && styles.plannerCheckCircleTextChecked,
                                          ]}
                                        >
                                          {card.isChecked ? '✓' : ''}
                                        </Text>
                                      </Pressable>
                                    )
                                  ) : null}
                                </View>
                                {card.isAdded && !hasOptions ? (
                                  <View style={styles.inlineActions}>
                                    <Pressable style={styles.smallButton} onPress={() => openPlannerEditor(primary)}>
                                      <Text style={styles.smallButtonText}>Edit</Text>
                                    </Pressable>
                                    {primary ? (
                                      <Pressable
                                        style={styles.smallDangerButton}
                                        onPress={() => deletePlannerEntry(primary)}
                                      >
                                        <Text style={styles.smallDangerButtonText}>Delete</Text>
                                      </Pressable>
                                    ) : null}
                                  </View>
                                ) : hasOptions ? (
                                  <View style={styles.inlineActions}>
                                    <Pressable style={styles.smallButton} onPress={() => setPlannerCategoryCode(card.groupCode)}>
                                      <Text style={styles.smallButtonText}>Open</Text>
                                    </Pressable>
                                  </View>
                                ) : null}
                              </Pressable>
                            );
                          })}
                          {!filteredPlannerCategoryCards.length ? (
                            <Text style={styles.subtleText}>
                              No checklist items matched your search.
                            </Text>
                          ) : null}
                        </View>
                      )}
                    </View>
                  )}
                </View>
              </TouchableWithoutFeedback>
            </ScrollView>
          )
          )}
        </View>

        {renderNativeBottomTabs()}

        <Modal
          visible={showEstimatePicker}
          transparent
          animationType="slide"
          onRequestClose={() => setShowEstimatePicker(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.sectionTitle}>Select Job Reference</Text>
              <Text style={styles.subtleText}>Optional. List can be standalone without a job.</Text>
              <ScrollView style={styles.estimatePickerList}>
                {estimates.map((estimate) => (
                  <Pressable
                    key={estimate.id}
                    style={[
                      styles.savedCard,
                      shoppingEstimateRefId === estimate.id && styles.selectedCard,
                    ]}
                    onPress={() => {
                      setShoppingEstimateRefId(estimate.id);
                      setShoppingCatererId(estimate.caterer_id);
                      setShowEstimatePicker(false);
                    }}
                  >
                    <Text style={styles.savedTitle}>{estimate.job_name}</Text>
                    <Text style={styles.subtleText}>
                      #{estimate.estimate_number ?? estimate.id} • {estimate.caterer_name}
                    </Text>
                  </Pressable>
                ))}
                {!estimates.length ? (
                  <Text style={styles.subtleText}>No estimates available.</Text>
                ) : null}
              </ScrollView>
              <View style={styles.inlineActions}>
                <Pressable
                  style={styles.smallButton}
                  onPress={() => {
                    setShoppingEstimateRefId(null);
                    setShowEstimatePicker(false);
                  }}
                >
                  <Text style={styles.smallButtonText}>Clear</Text>
                </Pressable>
                <Pressable style={styles.smallButton} onPress={() => setShowEstimatePicker(false)}>
                  <Text style={styles.smallButtonText}>Close</Text>
                </Pressable>
              </View>
            </View>
          </View>
        </Modal>
        <Modal
          visible={shoppingItemEditorOpen}
          transparent
          animationType="slide"
          onRequestClose={closeShoppingItemEditor}
        >
          <View style={styles.modalBackdrop}>
            <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
              <View style={styles.modalCard}>
                <Text style={styles.sectionTitle}>Edit Item</Text>
                <Text style={styles.subtleText}>Update and save this shopping row.</Text>
                <TextInput
                  style={styles.input}
                  value={shoppingEditName}
                  onChangeText={setShoppingEditName}
                  placeholder="Item name"
                />
                <TextInput
                  style={styles.input}
                  value={shoppingEditType}
                  onChangeText={setShoppingEditType}
                  placeholder="Type (optional)"
                />
                <TextInput
                  style={styles.input}
                  value={shoppingEditQty}
                  onChangeText={setShoppingEditQty}
                  keyboardType="decimal-pad"
                  inputAccessoryViewID={Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined}
                  placeholder="Quantity"
                />
                <TextInput
                  style={styles.input}
                  value={shoppingEditUnit}
                  onChangeText={setShoppingEditUnit}
                  placeholder="Unit"
                />
                <View style={styles.inlineActions}>
                  <Pressable
                    style={[styles.primaryButton, savingShoppingEdit && styles.buttonDisabled]}
                    onPress={saveShoppingItemEdit}
                    disabled={savingShoppingEdit}
                  >
                    {savingShoppingEdit ? (
                      <ActivityIndicator color="#ffffff" />
                    ) : (
                      <Text style={styles.primaryButtonText}>Save</Text>
                    )}
                  </Pressable>
                  <Pressable style={styles.smallButton} onPress={closeShoppingItemEditor}>
                    <Text style={styles.smallButtonText}>Cancel</Text>
                  </Pressable>
                </View>
              </View>
            </TouchableWithoutFeedback>
          </View>
        </Modal>
        <Modal
          visible={plannerEditorVisible}
          animationType="slide"
          onRequestClose={closePlannerEditor}
        >
          <SafeAreaView style={styles.plannerEditorSafeArea} edges={['left', 'right', 'bottom']}>
            <KeyboardAvoidingView
              style={styles.flexOne}
              behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            >
              <View style={modalHeaderStyle}>
                <View style={styles.flexOne}>
                  <Text style={styles.sectionTitle}>
                    {plannerEditingEntryId ? 'Edit Planner Item' : 'Add Planner Item'}
                  </Text>
                  <Text style={styles.subtleText}>
                    {plannerCategoryCode ? 'Save returns you to the options screen.' : 'Save returns you to the checklist screen.'}
                  </Text>
                </View>
                <Pressable style={styles.smallButton} onPress={closePlannerEditor}>
                  <Text style={styles.smallButtonText}>Back</Text>
                </Pressable>
              </View>

              <ScrollView
                style={styles.plannerEditorScroll}
                contentContainerStyle={styles.plannerEditorScrollContent}
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="on-drag"
              >
                <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
                  <View style={styles.plannerEditorBody}>
                    {activePlannerSectionConfig ? (
                      <>
                        <View style={styles.plannerVariableCard}>
                          <Text style={styles.savedTitle}>
                            {activePlannerEditorGroup?.label || 'Planner Item'}
                          </Text>
                          {activePlannerEditorOptionLabel ? (
                            <Text style={styles.subtleText}>{activePlannerEditorOptionLabel}</Text>
                          ) : null}
                          <Text style={styles.subtleText}>
                            {plannerEditingEntryId
                              ? 'Update variables for this item.'
                              : 'Enter variables for this item.'}
                          </Text>
                        </View>
                        {activePlannerEditorFields.map((field) => {
                          const value = plannerEditorValues[field.code] || '';
                          const fieldCode = field.code.toLowerCase();
                          const fieldLabel = field.label.toLowerCase();
                          const isColorField = fieldCode.includes('color');
                          const isPriceField =
                            fieldCode.includes('price') ||
                            fieldCode.includes('cost') ||
                            fieldCode.includes('amount');
                          const isQtyField =
                            fieldCode.includes('qty') ||
                            fieldCode.includes('quantity') ||
                            fieldCode.includes('count');
                          const isOrderListField =
                            plannerSection === 'ORDERS' &&
                            !field.multiline &&
                            !isPriceField &&
                            !isQtyField &&
                            !fieldCode.includes('supplier') &&
                            !fieldCode.includes('note') &&
                            (fieldCode.includes('type') ||
                              fieldCode.includes('item') ||
                              fieldCode.includes('bread') ||
                              fieldLabel.includes('type') ||
                              fieldLabel.includes('item') ||
                              fieldLabel.includes('bread'));
                          const orderListValues = isOrderListField
                            ? plannerSplitMultiValue(value)
                            : [];
                          const orderListKeys = new Set(
                            orderListValues.map((row) => row.toLowerCase()),
                          );
                          const orderListDraft = plannerEditorFieldDraftValues[field.code] || '';
                          const memorySuggestions =
                            plannerSection && plannerEditorGroupCode
                              ? plannerSuggestionsForField(
                                  plannerSection,
                                  plannerEditorGroupCode,
                                  plannerEditorItemCode,
                                  field.code,
                                  isOrderListField ? '' : value,
                                ).slice(0, 10)
                              : [];
                          const suggestions = mergeOptionValues(
                            field.valueOptions,
                            memorySuggestions,
                            isColorField ? DEFAULT_PLANNER_COLOR_VALUES : undefined,
                            isPriceField ? DEFAULT_PLANNER_PRICE_VALUES : undefined,
                            isQtyField ? DEFAULT_PLANNER_QTY_VALUES : undefined,
                          ).slice(0, 14);
                          const selectedColorValues = plannerSplitMultiValue(value).map((row) =>
                            row.toLowerCase(),
                          );
                          return (
                            <View
                              key={`${plannerEditorGroupCode}-${field.code}`}
                              style={styles.plannerVariableCard}
                            >
                              <Text style={styles.savedTitle}>{field.label}</Text>
                              {isOrderListField ? (
                                <>
                                  <View style={styles.plannerListAddRow}>
                                    <TextInput
                                      style={[styles.input, styles.plannerListAddInput]}
                                      value={orderListDraft}
                                      onChangeText={(nextValue) =>
                                        setPlannerEditorFieldDraftValues((prev) => ({
                                          ...prev,
                                          [field.code]: nextValue,
                                        }))
                                      }
                                      placeholder={`Add ${field.label} item`}
                                      returnKeyType="done"
                                      onSubmitEditing={() =>
                                        plannerAddListFieldValue(field.code, orderListDraft)
                                      }
                                    />
                                    <Pressable
                                      style={styles.smallButton}
                                      onPress={() =>
                                        plannerAddListFieldValue(field.code, orderListDraft)
                                      }
                                    >
                                      <Text style={styles.smallButtonText}>+ Add Item</Text>
                                    </Pressable>
                                  </View>
                                  {orderListValues.length ? (
                                    <View style={styles.catalogItemWrap}>
                                      {orderListValues.map((item) => (
                                        <Pressable
                                          key={`${field.code}-item-${item}`}
                                          style={[styles.catalogTypePill, styles.plannerListItemPill]}
                                          onPress={() => plannerRemoveListFieldValue(field.code, item)}
                                        >
                                          <Text style={styles.catalogTypePillText}>{item}</Text>
                                          <Text style={styles.plannerListItemRemove}>×</Text>
                                        </Pressable>
                                      ))}
                                    </View>
                                  ) : (
                                    <Text style={styles.subtleText}>
                                      No items added yet. Use Add Item to build this order.
                                    </Text>
                                  )}
                                </>
                              ) : (
                                <TextInput
                                  style={[styles.input, field.multiline ? styles.noteInput : null]}
                                  value={value}
                                  onChangeText={(nextValue) =>
                                    setPlannerEditorValues((prev) => ({
                                      ...prev,
                                      [field.code]: nextValue,
                                    }))
                                  }
                                  placeholder={
                                    isColorField
                                      ? 'Add one or more colors (comma separated)'
                                      : field.placeholder || field.label
                                  }
                                  multiline={!!field.multiline}
                                  keyboardType={field.keyboardType || 'default'}
                                  inputAccessoryViewID={
                                    field.keyboardType === 'decimal-pad' && Platform.OS === 'ios'
                                      ? NUMERIC_INPUT_ACCESSORY_ID
                                      : undefined
                                  }
                                />
                              )}
                              {suggestions.length ? (
                                <View style={styles.catalogItemWrap}>
                                  {suggestions.map((suggestion) => {
                                    const colorHex = isColorField
                                      ? plannerColorHexForValue(suggestion)
                                      : '';
                                    const selected = isColorField
                                      ? selectedColorValues.includes(suggestion.toLowerCase())
                                      : isOrderListField
                                        ? orderListKeys.has(suggestion.toLowerCase())
                                      : value.trim().toLowerCase() === suggestion.toLowerCase();
                                    return (
                                      <Pressable
                                        key={`${plannerEditorGroupCode}-${field.code}-${suggestion}`}
                                        style={[
                                          styles.catalogTypePill,
                                          colorHex ? styles.plannerColorPill : null,
                                          colorHex ? { backgroundColor: colorHex } : null,
                                          selected && !colorHex ? styles.selectedPill : null,
                                          selected && colorHex ? styles.plannerColorPillSelected : null,
                                        ]}
                                        onPress={() =>
                                          isOrderListField
                                            ? plannerToggleListFieldValue(field.code, suggestion)
                                            : plannerApplySuggestion(field.code, suggestion)
                                        }
                                      >
                                        <Text
                                          style={[
                                            styles.catalogTypePillText,
                                            colorHex
                                              ? {
                                                  color: plannerTextColorForBackground(colorHex),
                                                }
                                              : null,
                                            selected && !colorHex ? styles.selectedPillText : null,
                                          ]}
                                        >
                                          {isPriceField && !suggestion.includes(SHEKEL_SYMBOL)
                                            ? `${SHEKEL_SYMBOL}${suggestion}`
                                            : suggestion}
                                        </Text>
                                      </Pressable>
                                    );
                                  })}
                                </View>
                              ) : null}
                            </View>
                          );
                        })}

                        <View style={styles.plannerVariableCard}>
                          <Text style={styles.savedTitle}>Notes</Text>
                          <TextInput
                            style={[styles.input, styles.noteInput]}
                            value={plannerEditorNotes}
                            onChangeText={setPlannerEditorNotes}
                            multiline
                            placeholder="Notes (optional)"
                          />
                        </View>

                        <View style={styles.plannerVariableCard}>
                          <View style={styles.headerRow}>
                            <Text style={styles.savedTitle}>Checklist</Text>
                            <Pressable
                              style={[styles.smallButton, plannerEditorChecked && styles.selectedPill]}
                              onPress={() => setPlannerEditorChecked((prev) => !prev)}
                            >
                              <Text
                                style={[
                                  styles.smallButtonText,
                                  plannerEditorChecked && styles.selectedPillText,
                                ]}
                              >
                                {plannerEditorChecked ? 'Checked' : 'Mark as checked'}
                              </Text>
                            </Pressable>
                          </View>
                        </View>

                        <View style={styles.plannerVariableCard}>
                          <View style={styles.headerRow}>
                            <Text style={styles.savedTitle}>Variable Cards</Text>
                            <Pressable
                              style={styles.smallButton}
                              onPress={() => setPlannerFieldCardsManagerOpen((prev) => !prev)}
                            >
                              <Text style={styles.smallButtonText}>
                                {plannerFieldCardsManagerOpen ? 'Close Manager' : 'Manage Cards'}
                              </Text>
                            </Pressable>
                          </View>
                          <Text style={styles.subtleText}>
                            {plannerEditorFieldCards.length
                              ? `${plannerEditorFieldCards.length} cards configured for this option.`
                              : 'No variable cards configured yet.'}
                          </Text>
                          {plannerFieldCardsManagerOpen ? (
                            <View style={styles.savedList}>
                              <View style={styles.inlineActions}>
                                <Pressable style={styles.smallButton} onPress={addPlannerEditorFieldCard}>
                                  <Text style={styles.smallButtonText}>+ Add Card</Text>
                                </Pressable>
                              </View>
                              {[...plannerEditorFieldCards]
                                .sort((a, b) => a.sortOrder - b.sortOrder)
                                .map((row, index, rows) => {
                                  const values = mergeOptionValues(
                                    plannerSplitMultiValue(row.valueOptionsText || ''),
                                  );
                                  return (
                                    <View key={row.id} style={styles.plannerFieldCardRow}>
                                      <View style={styles.plannerFieldCardMetaRow}>
                                        <Text style={styles.subtleText}>Card {index + 1}</Text>
                                        <View style={styles.inlineActions}>
                                          <Pressable
                                            style={[styles.smallButton, index === 0 && styles.buttonDisabled]}
                                            onPress={() => movePlannerEditorFieldCard(row.id, 'up')}
                                            disabled={index === 0}
                                          >
                                            <Text style={styles.smallButtonText}>Up</Text>
                                          </Pressable>
                                          <Pressable
                                            style={[
                                              styles.smallButton,
                                              index === rows.length - 1 && styles.buttonDisabled,
                                            ]}
                                            onPress={() => movePlannerEditorFieldCard(row.id, 'down')}
                                            disabled={index === rows.length - 1}
                                          >
                                            <Text style={styles.smallButtonText}>Down</Text>
                                          </Pressable>
                                          <Pressable
                                            style={styles.smallDangerButton}
                                            onPress={() => deletePlannerEditorFieldCard(row.id)}
                                          >
                                            <Text style={styles.smallDangerButtonText}>Remove</Text>
                                          </Pressable>
                                        </View>
                                      </View>

                                      <TextInput
                                        style={styles.input}
                                        value={row.fieldLabel}
                                        onChangeText={(nextValue) => {
                                          const previousCode = row.fieldCode || '';
                                          const nextCode = normalizePlannerCode(nextValue || '');
                                          updatePlannerEditorFieldCard(row.id, {
                                            fieldLabel: nextValue,
                                            fieldCode: nextCode,
                                          });
                                          if (
                                            previousCode &&
                                            nextCode &&
                                            previousCode.toLowerCase() !== nextCode.toLowerCase()
                                          ) {
                                            setPlannerEditorValues((prev) => {
                                              const previousValue = prev[previousCode] || '';
                                              if (!previousValue) {
                                                return prev;
                                              }
                                              const mergedValues = mergeOptionValues(
                                                plannerSplitMultiValue(prev[nextCode] || ''),
                                                plannerSplitMultiValue(previousValue),
                                              );
                                              const nextState = { ...prev };
                                              delete nextState[previousCode];
                                              nextState[nextCode] = mergedValues.join(', ');
                                              return nextState;
                                            });
                                            setPlannerEditorFieldDraftValues((prev) => {
                                              const previousValue = prev[previousCode] || '';
                                              if (!previousValue || prev[nextCode]) {
                                                return prev;
                                              }
                                              const nextState = { ...prev };
                                              delete nextState[previousCode];
                                              nextState[nextCode] = previousValue;
                                              return nextState;
                                            });
                                          }
                                        }}
                                        placeholder="Field name"
                                      />
                                      <TextInput
                                        style={styles.input}
                                        value={row.valueOptionsText}
                                        onChangeText={(nextValue) =>
                                          updatePlannerEditorFieldCard(row.id, {
                                            valueOptionsText: nextValue,
                                          })
                                        }
                                        placeholder="Pill values (comma separated)"
                                      />
                                      {values.length ? (
                                        <View style={styles.catalogItemWrap}>
                                          {values.map((value) => (
                                            <View
                                              key={`${row.id}-value-${value}`}
                                              style={styles.catalogTypePill}
                                            >
                                              <Text style={styles.catalogTypePillText}>{value}</Text>
                                            </View>
                                          ))}
                                        </View>
                                      ) : null}
                                    </View>
                                  );
                                })}
                              {!plannerEditorFieldCards.length ? (
                                <Text style={styles.subtleText}>
                                  No variable cards yet. Add one to define a new field.
                                </Text>
                              ) : null}
                              <View style={styles.plannerManagerFooter}>
                                <Pressable
                                  style={[
                                    styles.smallAccentButton,
                                    savingPlanner && styles.buttonDisabled,
                                  ]}
                                  onPress={savePlannerFieldCardEdits}
                                  disabled={savingPlanner}
                                >
                                  <Text style={styles.smallAccentButtonText}>
                                    Save Card Edits
                                  </Text>
                                </Pressable>
                              </View>
                            </View>
                          ) : null}
                        </View>
                      </>
                    ) : null}
                  </View>
                </TouchableWithoutFeedback>
              </ScrollView>

              <View style={styles.plannerEditorFooter}>
                <Pressable
                  style={[styles.primaryButton, savingPlanner && styles.buttonDisabled]}
                  onPress={savePlannerEntry}
                  disabled={savingPlanner}
                >
                  {savingPlanner ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Save Item</Text>
                  )}
                </Pressable>
                <Pressable style={styles.smallButton} onPress={closePlannerEditor}>
                  <Text style={styles.smallButtonText}>Cancel</Text>
                </Pressable>
              </View>
            </KeyboardAvoidingView>
          </SafeAreaView>
        </Modal>
        {Platform.OS === 'ios' ? (
          <InputAccessoryView nativeID={NUMERIC_INPUT_ACCESSORY_ID}>
            <View style={styles.inputAccessoryBar}>
              <Pressable style={styles.smallButton} onPress={() => Keyboard.dismiss()}>
                <Text style={styles.smallButtonText}>Done</Text>
              </Pressable>
            </View>
          </InputAccessoryView>
        ) : null}
        {shellModals}
        <StatusBar style="dark" />
      </SafeAreaView>
      </GestureHandlerRootView>
    );
  }

  return (
    <GestureHandlerRootView style={styles.flexOne}>
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.flexOne}>
        <ScrollView contentContainerStyle={tabbedContentWrapStyle}>
          <View style={styles.appHeader}>
            <View style={styles.appHeaderLeft}>
              <Pressable style={styles.headerIconButton} onPress={handleBackChevron}>
                <Text style={styles.headerIconGlyph}>‹</Text>
              </Pressable>
              <View style={styles.appHeaderTitleWrap}>
                <Text style={styles.appHeaderTitle}>{mainTab === 'staff' ? 'Staff' : 'Expenses'}</Text>
                <Text style={styles.appHeaderSubtitle}>{selectedEstimate.job_name}</Text>
              </View>
            </View>
            <View style={styles.appHeaderRight}>
              <Pressable
                style={styles.headerIconButton}
                onPress={() => {
                  if (mainTab === 'staff') {
                    loadStaffSummary(selectedEstimate.id);
                  } else {
                    loadEntries(selectedEstimate.id);
                  }
                }}
              >
                <RefreshCcw size={18} color="#64748b" />
              </Pressable>
              <Pressable style={styles.headerIconButton} onPress={() => setMenuOpen(true)}>
                <CircleEllipsis size={18} color="#64748b" />
              </Pressable>
            </View>
          </View>

          <View style={styles.sectionCard}>
            <Text style={styles.sectionTitle}>{selectedEstimate.job_name}</Text>
            <Text style={styles.subtleText}>
              {selectedEstimate.customer_name} • {formatDate(selectedEstimate.event_date)}
            </Text>
            <Text style={styles.subtleText}>{selectedEstimate.event_location || 'No location'}</Text>
            {selectedEstimate.can_view_billing ? (
              <Text style={styles.subtleText}>Estimate total: {formatShekel(selectedEstimate.grand_total || '0.00')}</Text>
            ) : null}
          </View>

          {mainTab === 'expenses' ? (
            <>
              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Add Expenses</Text>
                <Text style={styles.subtleText}>
                  Use camera or gallery for the receipt, then record voice. Type the expense line under each item.
                </Text>
                {selectedEstimate.can_add_expenses ? (
                  <View style={styles.inlineActions}>
                    <Pressable style={styles.primaryButton} onPress={captureReceiptAndVoice}>
                      <Text style={styles.primaryButtonText}>Camera + Voice</Text>
                    </Pressable>
                    <Pressable style={styles.secondaryButton} onPress={pickReceiptFromGalleryAndVoice}>
                      <Text style={styles.secondaryButtonText}>Gallery + Voice</Text>
                    </Pressable>
                    <Pressable style={styles.secondaryButton} onPress={addManualDraft}>
                      <Text style={styles.secondaryButtonText}>+ Manual Expense</Text>
                    </Pressable>
                  </View>
                ) : (
                  <Text style={styles.subtleText}>
                    Your account can view expenses for this job but cannot add new expense entries.
                  </Text>
                )}

                {recordingPhotoUri && (
                  <View style={styles.recordingBar}>
                    <Text style={styles.recordingText}>Recording voice note... {recordingSeconds}s</Text>
                    <View style={styles.inlineActions}>
                      <Pressable style={styles.smallDangerButton} onPress={stopRecordingAndCreateDraft}>
                        <Text style={styles.smallDangerButtonText}>Stop & Add</Text>
                      </Pressable>
                      <Pressable style={styles.smallButton} onPress={cancelRecording}>
                        <Text style={styles.smallButtonText}>Cancel</Text>
                      </Pressable>
                    </View>
                  </View>
                )}

                {drafts.map((draft) => (
                  <View key={draft.localId} style={styles.draftCard}>
                    <View style={styles.draftHeaderRow}>
                      <Text style={styles.draftTitle}>
                        {draft.manualOnly ? 'Manual Entry' : 'Receipt + Voice Entry'}
                      </Text>
                      <Pressable onPress={() => removeDraft(draft.localId)}>
                        <Text style={styles.deleteText}>Remove</Text>
                      </Pressable>
                    </View>

                    {!draft.manualOnly && draft.receiptUri && (
                      <Image source={{ uri: draft.receiptUri }} style={styles.receiptPreview} />
                    )}
                    {!draft.manualOnly && draft.voiceDurationSeconds ? (
                      <Text style={styles.subtleText}>Voice note: {draft.voiceDurationSeconds}s</Text>
                    ) : null}
                    {!draft.manualOnly && !draft.voiceUri ? (
                      <Text style={styles.subtleText}>Voice note not attached yet.</Text>
                    ) : null}

                    <TextInput
                      style={styles.input}
                      value={draft.expenseText}
                      onChangeText={(value) => updateDraft(draft.localId, { expenseText: value })}
                      placeholder="Expense line (e.g. Produce market)"
                    />
                    <Text style={styles.labelInline}>Total amount (₪)</Text>
                    <TextInput
                      style={styles.input}
                      value={draft.expenseAmount}
                      onChangeText={(value) => updateDraft(draft.localId, { expenseAmount: value })}
                      keyboardType="decimal-pad"
                      placeholder="Total amount (₪)"
                    />
                    <TextInput
                      style={[styles.input, styles.noteInput]}
                      value={draft.noteText}
                      onChangeText={(value) => updateDraft(draft.localId, { noteText: value })}
                      multiline
                      placeholder="Extra note or transcript"
                    />
                  </View>
                ))}

                {!drafts.length && <Text style={styles.subtleText}>No pending items yet.</Text>}

                <Pressable
                  style={[styles.primaryButton, (!drafts.length || uploading || !selectedEstimate.can_add_expenses) && styles.buttonDisabled]}
                  onPress={uploadDrafts}
                  disabled={!drafts.length || uploading || !selectedEstimate.can_add_expenses}
                >
                  {uploading ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Save {drafts.length} Expense(s)</Text>
                  )}
                </Pressable>
              </View>

              <View style={styles.sectionCard}>
                <View style={styles.headerRow}>
                  <Text style={styles.sectionTitle}>Saved in Additional Info Tab</Text>
                  <Pressable
                    style={styles.smallButton}
                    onPress={() => loadEntries(selectedEstimate.id)}
                  >
                    <Text style={styles.smallButtonText}>Refresh</Text>
                  </Pressable>
                </View>

                {loadingEntries ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {savedEntries.map((entry) => (
                      <View key={entry.id} style={styles.savedCard}>
                        <Text style={styles.savedTitle}>
                          {entry.expense_text || (entry.is_manual_only ? 'Manual expense' : 'Receipt expense')}
                        </Text>
                        <Text style={styles.subtleText}>
                          {entry.expense_amount ? formatShekel(entry.expense_amount) : 'No amount'} •{' '}
                          {formatDate(entry.created_at)}
                        </Text>
                        {entry.note_text ? <Text style={styles.subtleText}>{entry.note_text}</Text> : null}

                        <View style={styles.inlineActions}>
                          {entry.receipt_image_url ? (
                            <Pressable
                              style={styles.smallButton}
                              onPress={() => Linking.openURL(entry.receipt_image_url)}
                            >
                              <Text style={styles.smallButtonText}>Receipt</Text>
                            </Pressable>
                          ) : null}
                          {entry.voice_note_url ? (
                            <Pressable
                              style={styles.smallButton}
                              onPress={() => Linking.openURL(entry.voice_note_url)}
                            >
                              <Text style={styles.smallButtonText}>Voice</Text>
                            </Pressable>
                          ) : null}
                        </View>
                      </View>
                    ))}

                    {!savedEntries.length && (
                      <Text style={styles.subtleText}>No saved entries for this estimate yet.</Text>
                    )}
                  </View>
                )}
              </View>
            </>
          ) : (
            <>
              <View style={styles.sectionCard}>
                <View style={styles.headerRow}>
                  <Text style={styles.sectionTitle}>Staff QR Codes</Text>
                  <Pressable
                    style={styles.smallButton}
                    onPress={() => loadStaffSummary(selectedEstimate.id)}
                  >
                    <Text style={styles.smallButtonText}>Refresh</Text>
                  </Pressable>
                </View>
                <Text style={styles.subtleText}>
                  Staff scan role QR code to punch in and out on this job.
                </Text>

                {loadingStaff ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {staffRoleOptions.map((role) => (
                      <Pressable
                        key={role.code}
                        style={styles.roleCard}
                        onPress={() => setActiveQrRole(role)}
                      >
                        <Text style={styles.savedTitle}>{role.label}</Text>
                        <Text style={styles.linkText}>Open QR Code</Text>
                      </Pressable>
                    ))}
                    {!staffRoleOptions.length && (
                      <Text style={styles.subtleText}>No staff role options available yet.</Text>
                    )}
                  </View>
                )}
              </View>

              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Staff Totals</Text>
                <Text style={styles.subtleText}>Total staff cost: {formatShekel(staffTotalCost)}</Text>
                <Text style={styles.subtleText}>Unapplied staff cost: {formatShekel(unappliedStaffCost)}</Text>
                <Pressable
                  style={[
                    styles.primaryButton,
                    (applyingStaffCosts || Number.parseFloat(unappliedStaffCost) <= 0) && styles.buttonDisabled,
                  ]}
                  onPress={applyStaffCostsToExpenses}
                  disabled={applyingStaffCosts || Number.parseFloat(unappliedStaffCost) <= 0}
                >
                  {applyingStaffCosts ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Apply staff costs to expense page</Text>
                  )}
                </Pressable>
              </View>

              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Staff Records</Text>
                {loadingStaff ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {staffEntries.map((entry) => (
                      <View key={entry.id} style={styles.savedCard}>
                        <Text style={styles.savedTitle}>
                          {entry.worker_first_name} • {entry.role_label}
                        </Text>
                        <Text style={styles.subtleText}>In: {formatDateTime(entry.punched_in_at)}</Text>
                        <Text style={styles.subtleText}>
                          Out: {entry.punched_out_at ? formatDateTime(entry.punched_out_at) : 'Still active'}
                        </Text>
                        <Text style={styles.subtleText}>
                          Hours: {entry.total_hours} • Cost: {formatShekel(entry.total_cost)}
                        </Text>
                        <Text style={styles.subtleText}>
                          {entry.applied_to_expenses
                            ? `Applied to expense #${entry.expense_entry_id ?? '-'}`
                            : 'Not applied to expenses yet'}
                        </Text>
                      </View>
                    ))}
                    {!staffEntries.length && (
                      <Text style={styles.subtleText}>No staff records for this estimate yet.</Text>
                    )}
                  </View>
                )}
              </View>
            </>
          )}
        </ScrollView>

        {renderNativeBottomTabs()}
      </View>

      <Modal
        visible={!!activeQrRole}
        transparent
        animationType="slide"
        onRequestClose={() => setActiveQrRole(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.sectionTitle}>{activeQrRole?.label || 'Staff QR'}</Text>
            {activeQrRole?.qr_image_url ? (
              <Image source={{ uri: activeQrRole.qr_image_url }} style={styles.qrImage} />
            ) : null}
            <Text style={styles.subtleText}>
              Staff scan this code for punch in/out on this job.
            </Text>
            <View style={styles.inlineActions}>
              <Pressable
                style={styles.primaryButton}
                onPress={() => {
                  if (activeQrRole?.punch_url) {
                    Linking.openURL(activeQrRole.punch_url);
                  }
                }}
              >
                <Text style={styles.primaryButtonText}>Open Punch Page</Text>
              </Pressable>
              <Pressable style={styles.smallButton} onPress={() => setActiveQrRole(null)}>
                <Text style={styles.smallButtonText}>Close</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
      {shellModals}
      <StatusBar style="dark" />
    </SafeAreaView>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  flexOne: {
    flex: 1,
  },
  screen: {
    flex: 1,
    backgroundColor: '#f7f7f7',
  },
  screenCenter: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: '#f7f7f7',
  },
  contentWrap: {
    paddingHorizontal: 14,
    paddingTop: 8,
    gap: 10,
    paddingBottom: 12,
  },
  contentTapDismissArea: {
    gap: 14,
  },
  loginCard: {
    margin: 18,
    marginTop: 56,
    borderRadius: 18,
    backgroundColor: '#ffffff',
    padding: 20,
    gap: 10,
    shadowColor: '#0f172a',
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
  },
  appTitle: {
    fontSize: 32,
    fontWeight: '700',
    color: '#0f172a',
  },
  label: {
    marginTop: 6,
    fontSize: 13,
    fontWeight: '600',
    color: '#1f2937',
  },
  labelInline: {
    marginTop: 2,
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
  },
  input: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#f8fafc',
  },
  noteInput: {
    minHeight: 72,
    textAlignVertical: 'top',
  },
  primaryButton: {
    backgroundColor: '#0f766e',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 130,
  },
  primaryButtonText: {
    color: '#ffffff',
    fontWeight: '700',
  },
  secondaryButton: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#0f766e',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 130,
  },
  secondaryButtonText: {
    color: '#0f766e',
    fontWeight: '700',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  sectionCard: {
    borderRadius: 12,
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    gap: 8,
  },
  builderEstimateHeaderRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
  builderEstimateHeaderMain: {
    flex: 1,
    gap: 2,
  },
  builderEstimateHeaderMainMulti: {
    flex: 0.9,
    minWidth: 120,
  },
  builderEstimatePriceGrid: {
    alignItems: 'flex-end',
    justifyContent: 'flex-start',
    gap: 8,
  },
  builderEstimatePriceGridMulti: {
    flex: 1.1,
    minWidth: 170,
    alignItems: 'stretch',
    justifyContent: 'flex-start',
  },
  builderEstimatePriceRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 8,
  },
  builderEstimatePriceCard: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    paddingHorizontal: 10,
    paddingVertical: 7,
    minWidth: 110,
  },
  builderEstimatePriceCardMulti: {
    flex: 1,
    minWidth: 0,
    minHeight: 72,
  },
  builderEstimatePriceCardSpacer: {
    flex: 1,
  },
  builderEstimatePriceMealName: {
    color: '#0f172a',
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
    width: '100%',
  },
  builderEstimatePriceLabel: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: '600',
    textAlign: 'center',
  },
  builderEstimatePriceValue: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  builderMealOverrideCard: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 8,
  },
  builderMealOverrideRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  builderMealOverrideInput: {
    flex: 1,
    marginBottom: 0,
  },
  builderMealGuestInput: {
    flex: 1,
    marginBottom: 0,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: '#0f172a',
    flexShrink: 1,
  },
  subtleText: {
    color: '#64748b',
    fontSize: 13,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  headerRowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 16,
    paddingTop: 6,
    paddingBottom: 6,
  },
  navSpacer: {
    width: 64,
  },
  headerTitleCenter: {
    flex: 1,
    textAlign: 'center',
  },
  inlineActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
    flexShrink: 0,
  },
  listHeaderTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  listHeaderTitle: {
    flex: 1,
    minWidth: 0,
  },
  listHeaderMetaRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
  },
  listHeaderMetaText: {
    flex: 1,
    gap: 4,
  },
  smallButton: {
    borderWidth: 1,
    borderColor: '#94a3b8',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 7,
    backgroundColor: '#ffffff',
  },
  smallButtonText: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: '600',
  },
  smallAccentButton: {
    borderRadius: 10,
    borderColor: '#0f766e',
    backgroundColor: '#ecfeff',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  smallAccentButtonText: {
    color: '#0f766e',
    fontSize: 12,
    fontWeight: '700',
  },
  smallDangerButton: {
    borderRadius: 10,
    backgroundColor: '#b91c1c',
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  smallDangerButtonText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700',
  },
  estimateBuilderSaveButton: {
    minWidth: 210,
  },
  estimateBuilderFooter: {
    justifyContent: 'center',
  },
  jobsListWrap: {
    padding: 16,
    gap: 12,
    paddingBottom: 12,
  },
  jobCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    backgroundColor: '#ffffff',
    padding: 11,
    gap: 4,
  },
  jobTitle: {
    fontSize: 17,
    fontWeight: '500',
    color: '#0f172a',
  },
  plannerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  plannerIconCard: {
    width: '48%',
    minHeight: 132,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  plannerIconBadge: {
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plannerSectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  plannerSectionTitleTextWrap: {
    flex: 1,
    minWidth: 0,
  },
  plannerSectionGlyph: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plannerIconLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
    textAlign: 'center',
  },
  plannerIconMeta: {
    fontSize: 12,
    color: '#475569',
    textAlign: 'center',
  },
  plannerChecklistCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  plannerChecklistCardPending: {
    backgroundColor: '#f1f5f9',
    borderColor: '#cbd5e1',
    opacity: 0.72,
  },
  plannerChecklistCardDone: {
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
  },
  plannerChecklistMain: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  plannerChecklistBody: {
    flex: 1,
    gap: 4,
  },
  plannerChecklistTitleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  plannerChecklistIconBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
    alignItems: 'center',
    justifyContent: 'center',
  },
  plannerChecklistTitleWrap: {
    flex: 1,
    gap: 2,
  },
  plannerChecklistTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
  },
  plannerChecklistSubtitle: {
    fontSize: 12,
    color: '#64748b',
    fontWeight: '600',
  },
  plannerChecklistMissingText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#64748b',
  },
  plannerChecklistSummary: {
    gap: 2,
  },
  plannerChecklistPlaceholder: {
    color: '#64748b',
    fontSize: 13,
  },
  plannerEntryCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 8,
  },
  plannerEntryCardChecked: {
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
  },
  plannerEntryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  plannerCheckCircle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: '#94a3b8',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ffffff',
  },
  plannerCheckCircleChecked: {
    backgroundColor: '#0f766e',
    borderColor: '#0f766e',
  },
  plannerCheckCircleText: {
    color: '#94a3b8',
    fontSize: 14,
    fontWeight: '700',
  },
  plannerCheckCircleTextChecked: {
    color: '#ffffff',
  },
  plannerEntryTitleWrap: {
    flex: 1,
    gap: 2,
  },
  plannerEntryDataList: {
    gap: 4,
    paddingLeft: 4,
  },
  plannerFieldBlock: {
    gap: 6,
  },
  plannerVariableCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 8,
  },
  plannerAddOptionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  plannerAddOptionInput: {
    flex: 1,
  },
  plannerListAddRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  plannerListAddInput: {
    flex: 1,
  },
  plannerListItemPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  plannerListItemRemove: {
    color: '#b91c1c',
    fontWeight: '700',
  },
  plannerFieldCardRow: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 8,
  },
  plannerFieldCardMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  plannerManagerFooter: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingTop: 2,
  },
  plannerEditorSafeArea: {
    flex: 1,
    backgroundColor: '#ffffff',
  },
  plannerEditorHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#d1d5db',
    backgroundColor: '#ffffff',
  },
  plannerEditorScroll: {
    flex: 1,
  },
  plannerEditorScrollContent: {
    padding: 16,
    paddingBottom: 110,
  },
  plannerEditorBody: {
    gap: 10,
  },
  plannerEditorFooter: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopWidth: 1,
    borderTopColor: '#d1d5db',
    backgroundColor: '#ffffff',
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  recordingBar: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#fecaca',
    backgroundColor: '#fff1f2',
    padding: 10,
    gap: 8,
  },
  recordingText: {
    color: '#9f1239',
    fontWeight: '700',
  },
  draftCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    padding: 10,
    gap: 8,
    backgroundColor: '#f8fafc',
  },
  draftHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  draftTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
  deleteText: {
    color: '#b91c1c',
    fontWeight: '700',
  },
  receiptPreview: {
    width: '100%',
    height: 170,
    borderRadius: 10,
    resizeMode: 'cover',
    backgroundColor: '#e2e8f0',
  },
  savedList: {
    gap: 10,
  },
  savedCard: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    backgroundColor: '#ffffff',
    padding: 10,
    gap: 6,
  },
  builderOptionRow: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 10,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  builderOptionBody: {
    flex: 1,
    gap: 6,
  },
  listRowHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  listRowOpenArea: {
    flex: 1,
    gap: 2,
  },
  listDeleteButton: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#ef4444',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff1f2',
  },
  listDeleteButtonText: {
    color: '#b91c1c',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 16,
  },
  selectedCard: {
    borderColor: '#0f766e',
    backgroundColor: '#f0fdfa',
  },
  savedTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
  shoppingCategoryBlock: {
    gap: 8,
  },
  shoppingCategoryTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0f172a',
  },
  catalogCategoryBlock: {
    gap: 8,
  },
  catalogCategoryToggle: {
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    backgroundColor: '#f8fafc',
    paddingHorizontal: 10,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  catalogCategoryToggleActive: {
    borderColor: '#0f766e',
    backgroundColor: '#ecfeff',
  },
  catalogCategoryTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0f172a',
  },
  catalogCategoryTitleActive: {
    color: '#0f766e',
  },
  catalogCategoryToggleIcon: {
    fontSize: 16,
    fontWeight: '700',
    color: '#475569',
    lineHeight: 18,
  },
  catalogCategoryToggleIconActive: {
    color: '#0f766e',
  },
  catalogItemWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  catalogItemPill: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    backgroundColor: '#f8fafc',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  catalogItemPillText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#0f172a',
  },
  catalogTypePill: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#94a3b8',
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  catalogTypePillText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#0f172a',
  },
  plannerColorPill: {
    borderColor: '#64748b',
  },
  plannerColorPillSelected: {
    borderColor: '#0f172a',
    borderWidth: 2,
  },
  shoppingItemRow: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  shoppingItemTextWrap: {
    flex: 1,
    gap: 2,
  },
  shoppingItemMain: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
  shoppingItemRemove: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#ef4444',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff1f2',
  },
  shoppingItemRemoveText: {
    color: '#b91c1c',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 18,
  },
  selectedPill: {
    backgroundColor: '#0f766e',
    borderColor: '#0f766e',
  },
  selectedPillText: {
    color: '#ffffff',
  },
  estimatePickerList: {
    maxHeight: 360,
  },
  roleCard: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#99f6e4',
    backgroundColor: '#f0fdfa',
    padding: 12,
    gap: 6,
  },
  linkText: {
    color: '#0f766e',
    fontSize: 13,
    fontWeight: '700',
  },
  appHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingTop: 4,
    paddingBottom: 8,
    backgroundColor: '#f7f7f7',
    gap: 10,
  },
  appHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
    minWidth: 0,
  },
  appHeaderTitleWrap: {
    flex: 1,
    minWidth: 0,
    gap: 1,
  },
  appHeaderTitle: {
    fontSize: 22,
    color: '#0f172a',
    fontWeight: '600',
  },
  appHeaderSubtitle: {
    fontSize: 13,
    color: '#94a3b8',
  },
  appHeaderRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerIconButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerIconGlyph: {
    fontSize: 24,
    color: '#64748b',
    lineHeight: 24,
    marginTop: -1,
  },
  headerTextButton: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 10,
    backgroundColor: '#e2e8f0',
  },
  headerTextButtonLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
  },
  nativeContentWrap: {
    paddingHorizontal: 14,
    paddingTop: 8,
    paddingBottom: 12,
  },
  nativeContentInner: {
    gap: 12,
  },
  nativeScreenHeader: {
    gap: 4,
  },
  nativeScreenTitle: {
    fontSize: 22,
    fontWeight: '600',
    color: '#0f172a',
  },
  nativeScreenSubtitle: {
    fontSize: 13,
    color: '#94a3b8',
  },
  nativeHeaderActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingTop: 4,
  },
  nativeFormGroup: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    gap: 8,
  },
  nativeSectionHeading: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94a3b8',
    letterSpacing: 0.5,
  },
  nativeFormInline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  nativeInput: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#f8fafc',
  },
  nativeInputInline: {
    flex: 1,
  },
  nativeChipRow: {
    paddingVertical: 2,
    gap: 8,
  },
  nativeChip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
  },
  nativeChipSelected: {
    borderColor: '#0f766e',
    backgroundColor: '#ecfdf5',
  },
  nativeChipLabel: {
    fontSize: 12,
    color: '#334155',
  },
  nativeChipLabelSelected: {
    color: '#0f766e',
    fontWeight: '600',
  },
  inlinePrimaryAction: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    backgroundColor: '#0f766e',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  inlinePrimaryActionText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
  },
  nativeListLoading: {
    paddingVertical: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  nativeListGroupWrap: {
    gap: 10,
  },
  nativeSectionBlock: {
    gap: 8,
  },
  nativeListSurface: {
    borderRadius: 12,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    backgroundColor: '#ffffff',
  },
  nativeListDivider: {
    borderTopWidth: 1,
    borderTopColor: '#edf2f7',
  },
  nativeListRow: {
    minHeight: 62,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  nativeListRowPressed: {
    opacity: 0.65,
  },
  nativeListRowDimmed: {
    opacity: 0.5,
  },
  nativeListRowBody: {
    flex: 1,
    minWidth: 0,
    gap: 1,
  },
  nativeListRowTitle: {
    fontSize: 16,
    fontWeight: '500',
    color: '#0f172a',
  },
  nativeListRowSubtitle: {
    fontSize: 13,
    color: '#475569',
  },
  nativeListRowMeta: {
    fontSize: 13,
    color: '#94a3b8',
  },
  nativeListRowRight: {
    minWidth: 26,
    marginLeft: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  shoppingRowActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  shoppingRowEditButton: {
    borderRadius: 999,
    backgroundColor: '#e2e8f0',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  shoppingRowEditButtonText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '600',
  },
  shoppingRowDeleteButton: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: '#fecaca',
    backgroundColor: '#fff1f2',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shoppingRowDeleteButtonText: {
    color: '#b91c1c',
    fontSize: 15,
    fontWeight: '700',
    lineHeight: 16,
  },
  savedQuickChipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  savedQuickItemChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  savedQuickItemChipText: {
    fontSize: 13,
    color: '#334155',
    fontWeight: '500',
  },
  savedQuickAddWrap: {
    borderTopWidth: 1,
    borderTopColor: '#edf2f7',
    backgroundColor: '#f8fafc',
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
  },
  savedQuickAddMainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  savedQuickQtyStepButton: {
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  savedQuickQtyStepButtonText: {
    fontSize: 17,
    lineHeight: 19,
    color: '#334155',
    fontWeight: '600',
  },
  savedQuickQtyInput: {
    width: 68,
    height: 34,
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 8,
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    paddingVertical: 6,
    fontSize: 14,
    color: '#0f172a',
    textAlign: 'center',
  },
  savedQuickUnitButton: {
    minWidth: 72,
    height: 34,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  savedQuickUnitButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#334155',
  },
  savedQuickAddButton: {
    marginLeft: 'auto',
    borderRadius: 8,
    backgroundColor: '#0f766e',
    minWidth: 60,
    height: 34,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  savedQuickAddButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '700',
  },
  savedQuickUnitChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  swipeDeleteAction: {
    width: 86,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ef4444',
  },
  swipeDeleteActionText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '600',
  },
  nativeRowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  nativeCategoryToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  nativeCategoryChevron: {
    transform: [{ rotate: '0deg' }],
  },
  nativeCategoryChevronOpen: {
    transform: [{ rotate: '90deg' }],
  },
  nativeTabHost: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 60,
    elevation: 60,
  },
  nativeTabBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    borderTopColor: '#E5E5EA',
    borderTopWidth: 0.5,
    backgroundColor: '#ffffff',
    elevation: 0,
    shadowOpacity: 0,
    shadowRadius: 0,
    shadowOffset: { width: 0, height: 0 },
    shadowColor: '#000000',
    zIndex: 60,
    elevation: 60,
  },
  nativeTabButton: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: TAB_BAR_HEIGHT,
  },
  nativeTabItem: {
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
  },
  nativeTabIcon: {
    marginTop: 0,
    marginBottom: 0,
  },
  nativeTabLabel: {
    fontSize: 10,
    fontWeight: '500',
    marginTop: 2,
    marginBottom: 2,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.45)',
    justifyContent: 'center',
    padding: 18,
  },
  modalCard: {
    borderRadius: 16,
    backgroundColor: '#ffffff',
    padding: 16,
    gap: 10,
  },
  inputAccessoryBar: {
    borderTopWidth: 1,
    borderTopColor: '#d1d5db',
    backgroundColor: '#f8fafc',
    paddingHorizontal: 12,
    paddingVertical: 8,
    alignItems: 'flex-end',
  },
  qrImage: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 12,
    backgroundColor: '#f8fafc',
  },
});

export default function App() {
  return (
    <SafeAreaProvider>
      <AppShell />
    </SafeAreaProvider>
  );
}
