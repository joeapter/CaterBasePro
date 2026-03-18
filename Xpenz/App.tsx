import { StatusBar } from 'expo-status-bar';
import * as ImagePicker from 'expo-image-picker';
import * as SecureStore from 'expo-secure-store';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useMemo, useState } from 'react';
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
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableWithoutFeedback,
  View,
} from 'react-native';

type EstimateRow = {
  id: number;
  estimate_number: number | null;
  job_name: string;
  customer_name: string;
  event_type: string;
  event_date: string;
  event_location: string;
  caterer_id: number;
  caterer_name: string;
  currency: string;
  grand_total: string;
  expense_count: number;
  can_view_billing: boolean;
  can_add_expenses: boolean;
  can_manage_staff: boolean;
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

type ApiRequestError = Error & {
  status?: number;
};

const TOKEN_KEY = 'xpenz_token';
const BASE_URL_KEY = 'xpenz_base_url';
const DEFAULT_BASE_URL = 'https://www.caterbasepro.com';
const SHEKEL_SYMBOL = '₪';
const DEFAULT_SHOPPING_UNIT_OPTIONS = ['Kg', 'Pieces', 'Cans'];
const NUMERIC_INPUT_ACCESSORY_ID = 'xpenz-numeric-accessory';

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

export default function App() {
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
  const [mainTab, setMainTab] = useState<'jobs' | 'shopping'>('jobs');
  const [estimates, setEstimates] = useState<EstimateRow[]>([]);
  const [selectedEstimate, setSelectedEstimate] = useState<EstimateRow | null>(null);
  const [selectedJobTab, setSelectedJobTab] = useState<'expenses' | 'staff'>('expenses');
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
  const [newShoppingItemName, setNewShoppingItemName] = useState('');
  const [newShoppingItemType, setNewShoppingItemType] = useState('');
  const [newShoppingItemQuantity, setNewShoppingItemQuantity] = useState('');
  const [newShoppingItemUnit, setNewShoppingItemUnit] = useState('');
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<ShoppingCatalogItem | null>(null);
  const [catalogItemType, setCatalogItemType] = useState('');
  const [catalogItemQuantity, setCatalogItemQuantity] = useState('');
  const [catalogItemUnit, setCatalogItemUnit] = useState('');
  const [openCatalogCategory, setOpenCatalogCategory] = useState<string | null>(null);

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
          if (!categories.length) {
            return null;
          }
          if (prev && categories.some((category) => category.category === prev)) {
            return prev;
          }
          return categories[0].category;
        });
      } finally {
        setLoadingShoppingCatalog(false);
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

  const shoppingCatalogItemByName = useMemo(() => {
    const index = new Map<string, ShoppingCatalogItem>();
    for (const category of shoppingCatalogCategories) {
      for (const item of category.items) {
        const key = item.item_name.trim().toLowerCase();
        if (!key || index.has(key)) {
          continue;
        }
        index.set(key, item);
      }
    }
    return index;
  }, [shoppingCatalogCategories]);

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

  const knownUnitOptions = useMemo(() => {
    const fromCatalog = shoppingCatalogCategories.flatMap((category) =>
      category.items.flatMap((item) => item.unit_options || []),
    );
    return mergeOptionValues(
      DEFAULT_SHOPPING_UNIT_OPTIONS,
      fromCatalog,
      [newShoppingItemUnit],
    );
  }, [newShoppingItemUnit, shoppingCatalogCategories]);

  const selectedCatalogUnitOptions = useMemo(
    () =>
      mergeOptionValues(
        DEFAULT_SHOPPING_UNIT_OPTIONS,
        selectedCatalogItem?.unit_options || [],
        [catalogItemUnit],
      ),
    [catalogItemUnit, selectedCatalogItem],
  );

  useEffect(() => {
    const itemNameKey = newShoppingItemName.trim().toLowerCase();
    if (!itemNameKey || newShoppingItemUnit.trim()) {
      return;
    }
    const matchedItem = shoppingCatalogItemByName.get(itemNameKey);
    const rememberedUnit = (matchedItem?.last_used_unit || '').trim();
    if (!rememberedUnit) {
      return;
    }
    setNewShoppingItemUnit(rememberedUnit);
  }, [newShoppingItemName, newShoppingItemUnit, shoppingCatalogItemByName]);

  useEffect(() => {
    async function bootstrap() {
      try {
        const [savedToken, savedBase] = await Promise.all([
          SecureStore.getItemAsync(TOKEN_KEY),
          SecureStore.getItemAsync(BASE_URL_KEY),
        ]);
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
            setSelectedCatalogItem(null);
            setCatalogItemUnit('');
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
            setSelectedCatalogItem(null);
            setCatalogItemUnit('');
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
      setMainTab('jobs');
      setSelectedEstimate(null);
      setSelectedJobTab('expenses');
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
      setNewShoppingItemName('');
      setNewShoppingItemType('');
      setNewShoppingItemQuantity('');
      setNewShoppingItemUnit('');
      setSelectedCatalogItem(null);
      setCatalogItemType('');
      setCatalogItemQuantity('');
      setCatalogItemUnit('');
      setOpenCatalogCategory(null);
      setDrafts([]);
    }
  }, []);

  const handleSelectEstimate = useCallback(
    async (estimate: EstimateRow) => {
      setSelectedEstimate(estimate);
      setSelectedJobTab('expenses');
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

  const handleAddShoppingItem = useCallback(async () => {
    const added = await submitShoppingItem(
      newShoppingItemName,
      newShoppingItemType,
      newShoppingItemQuantity,
      newShoppingItemUnit,
    );
    if (!added) {
      return;
    }
    setNewShoppingItemName('');
    setNewShoppingItemType('');
    setNewShoppingItemQuantity('');
    setNewShoppingItemUnit('');
  }, [newShoppingItemName, newShoppingItemQuantity, newShoppingItemType, newShoppingItemUnit, submitShoppingItem]);

  const openCatalogItemEditor = useCallback((item: ShoppingCatalogItem) => {
    setSelectedCatalogItem(item);
    setCatalogItemType('');
    setCatalogItemQuantity('');
    setCatalogItemUnit((item.last_used_unit || '').trim());
  }, []);

  const handleAddCatalogItem = useCallback(async () => {
    if (!selectedCatalogItem) {
      return;
    }
    const added = await submitShoppingItem(
      selectedCatalogItem.item_name,
      catalogItemType,
      catalogItemQuantity,
      catalogItemUnit,
    );
    if (!added) {
      return;
    }
    setSelectedCatalogItem(null);
    setCatalogItemType('');
    setCatalogItemQuantity('');
    setCatalogItemUnit('');
  }, [catalogItemQuantity, catalogItemType, catalogItemUnit, selectedCatalogItem, submitShoppingItem]);

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
                setSelectedCatalogItem(null);
                setCatalogItemUnit('');
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

  if (!selectedEstimate) {
    return (
      <SafeAreaView style={styles.screen}>
        <View style={styles.headerRowTop}>
          <Text style={styles.sectionTitle}>
            {mainTab === 'jobs'
              ? 'Select Job'
              : selectedShoppingList
                ? selectedShoppingList.title
                : 'Shopping Lists'}
          </Text>
          <View style={styles.inlineActions}>
            <Pressable
              style={styles.smallButton}
              onPress={() => {
                if (mainTab === 'jobs') {
                  loadEstimates();
                  return;
                }
                if (selectedShoppingList) {
                  Promise.all([
                    loadShoppingListDetail(selectedShoppingList.id),
                    loadShoppingCatalog(),
                  ]);
                } else {
                  Promise.all([loadShoppingLists(), loadShoppingCatalog()]);
                }
              }}
            >
              <Text style={styles.smallButtonText}>Refresh</Text>
            </Pressable>
            <Pressable style={styles.smallButton} onPress={handleLogout}>
              <Text style={styles.smallButtonText}>Log Out</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.topTabs}>
          <Pressable
            style={[styles.topTabButton, mainTab === 'jobs' && styles.topTabButtonActive]}
            onPress={() => setMainTab('jobs')}
          >
            <Text style={[styles.topTabLabel, mainTab === 'jobs' && styles.topTabLabelActive]}>Jobs</Text>
          </Pressable>
          <Pressable
            style={[styles.topTabButton, mainTab === 'shopping' && styles.topTabButtonActive]}
            onPress={() => setMainTab('shopping')}
          >
            <Text style={[styles.topTabLabel, mainTab === 'shopping' && styles.topTabLabelActive]}>
              Shopping
            </Text>
          </Pressable>
        </View>

        {mainTab === 'jobs' ? (
          loadingJobs ? (
            <View style={styles.screenCenter}>
              <ActivityIndicator size="large" color="#0f766e" />
            </View>
          ) : (
            <ScrollView contentContainerStyle={styles.jobsListWrap}>
              {estimates.map((estimate) => (
                <Pressable
                  key={estimate.id}
                  style={styles.jobCard}
                  onPress={() => handleSelectEstimate(estimate)}
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
                </Pressable>
              ))}
              {!estimates.length && <Text style={styles.subtleText}>No estimates found for this account.</Text>}
            </ScrollView>
          )
        ) : (
          selectedShoppingList ? (
            <ScrollView
              contentContainerStyle={styles.contentWrap}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
                <View style={styles.contentTapDismissArea}>
              <View style={styles.sectionCard}>
                <View style={styles.listHeaderTopRow}>
                  <Text style={styles.sectionTitle}>{selectedShoppingList.title}</Text>
                  <Pressable
                    style={styles.smallButton}
                    onPress={() => {
                      setSelectedShoppingList(null);
                      setShoppingItems([]);
                      setSelectedCatalogItem(null);
                      setCatalogItemUnit('');
                      setShoppingListScreenMode('manage');
                    }}
                  >
                    <Text style={styles.smallButtonText}>Back to Lists</Text>
                  </Pressable>
                </View>
                <View style={styles.listHeaderMetaRow}>
                  <View style={styles.listHeaderMetaText}>
                    <Text style={styles.subtleText}>{selectedShoppingList.caterer_name}</Text>
                    {selectedShoppingList.estimate_label ? (
                      <Text style={styles.subtleText}>Linked job: {selectedShoppingList.estimate_label}</Text>
                    ) : (
                      <Text style={styles.subtleText}>No linked job (standalone list)</Text>
                    )}
                  </View>
                  <Pressable
                    style={[
                      styles.smallButton,
                      styles.smallAccentButton,
                    ]}
                    onPress={() => {
                      setShoppingListScreenMode((prev) => (prev === 'manage' ? 'list' : 'manage'));
                    }}
                  >
                    <Text style={styles.smallAccentButtonText}>
                      {shoppingListScreenMode === 'manage' ? 'Shopping List' : 'Manage'}
                    </Text>
                  </Pressable>
                </View>
              </View>

              {shoppingListScreenMode === 'manage' ? (
              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Add Item</Text>
                <TextInput
                  style={styles.input}
                  value={newShoppingItemName}
                  onChangeText={setNewShoppingItemName}
                  placeholder="Item (e.g. mushrooms)"
                />
                <TextInput
                  style={styles.input}
                  value={newShoppingItemType}
                  onChangeText={setNewShoppingItemType}
                  placeholder="Item type (optional, e.g. pack, fresh, jar)"
                />
                <TextInput
                  style={styles.input}
                  value={newShoppingItemQuantity}
                  onChangeText={setNewShoppingItemQuantity}
                  keyboardType="decimal-pad"
                  inputAccessoryViewID={
                    Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                  }
                  placeholder="Quantity (default 1)"
                />
                <TextInput
                  style={styles.input}
                  value={newShoppingItemUnit}
                  onChangeText={setNewShoppingItemUnit}
                  placeholder="Kg, Pieces, Cans"
                />
                <View style={styles.catalogItemWrap}>
                  {knownUnitOptions.map((option) => {
                    const selected = newShoppingItemUnit.trim().toLowerCase() === option.toLowerCase();
                    return (
                      <Pressable
                        key={`manual-unit-${option}`}
                        style={[styles.catalogTypePill, selected && styles.selectedPill]}
                        onPress={() => setNewShoppingItemUnit(option)}
                      >
                        <Text
                          style={[
                            styles.catalogTypePillText,
                            selected && styles.selectedPillText,
                          ]}
                        >
                          {option}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
                <Pressable
                  style={[styles.primaryButton, addingShoppingItem && styles.buttonDisabled]}
                  onPress={handleAddShoppingItem}
                  disabled={addingShoppingItem}
                >
                  {addingShoppingItem ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Add To List</Text>
                  )}
                </Pressable>
                <View style={styles.headerRow}>
                  <Text style={styles.sectionTitle}>Saved Items</Text>
                  <Pressable style={styles.smallButton} onPress={() => loadShoppingCatalog()}>
                    <Text style={styles.smallButtonText}>Refresh</Text>
                  </Pressable>
                </View>
                <Text style={styles.subtleText}>
                  Tap a saved item, then choose type, quantity, and unit.
                </Text>
                {loadingShoppingCatalog ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {shoppingCatalogCategories.map((category) => (
                      <View key={category.category} style={styles.catalogCategoryBlock}>
                        <Pressable
                          style={[
                            styles.catalogCategoryToggle,
                            openCatalogCategory === category.category && styles.catalogCategoryToggleActive,
                          ]}
                          onPress={() => setOpenCatalogCategory(category.category)}
                        >
                          <Text
                            style={[
                              styles.catalogCategoryTitle,
                              openCatalogCategory === category.category &&
                                styles.catalogCategoryTitleActive,
                            ]}
                          >
                            {category.category_label} ({category.items.length})
                          </Text>
                          <Text
                            style={[
                              styles.catalogCategoryToggleIcon,
                              openCatalogCategory === category.category &&
                                styles.catalogCategoryToggleIconActive,
                            ]}
                          >
                            {openCatalogCategory === category.category ? '−' : '+'}
                          </Text>
                        </Pressable>
                        {openCatalogCategory === category.category ? (
                          <View style={styles.catalogItemWrap}>
                            {category.items.map((item) => (
                              <Pressable
                                key={`${category.category}-${item.item_name}`}
                                style={styles.catalogItemPill}
                                onPress={() => openCatalogItemEditor(item)}
                              >
                                <Text style={styles.catalogItemPillText}>{item.item_name}</Text>
                              </Pressable>
                            ))}
                          </View>
                        ) : null}
                      </View>
                    ))}
                    {!shoppingCatalogCategories.length && (
                      <Text style={styles.subtleText}>
                        No saved items yet. Add a few items and they will appear here.
                      </Text>
                    )}
                  </View>
                )}
              </View>
              ) : null}

              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>
                  {shoppingListScreenMode === 'list' ? 'Shopping List' : 'Execute List'}
                </Text>
                <Text style={styles.subtleText}>Tap X to remove an item when purchased.</Text>
                {loadingShoppingItems ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {shoppingSections.map((section) => (
                      <View key={section.label} style={styles.shoppingCategoryBlock}>
                        <Text style={styles.shoppingCategoryTitle}>{section.label}</Text>
                        {section.items.map((item) => (
                          <View
                            key={item.id}
                            style={[
                              styles.shoppingItemRow,
                              removingShoppingItemId === item.id && styles.buttonDisabled,
                            ]}
                          >
                            <View style={styles.shoppingItemTextWrap}>
                              <Text style={styles.shoppingItemMain}>
                                {item.item_name}
                                {item.item_type ? ` (${item.item_type})` : ''}
                                {item.collaboration_note
                                  ? ` (${item.collaboration_note.toLowerCase()})`
                                  : ''}
                              </Text>
                              <Text style={styles.subtleText}>
                                Qty: {item.quantity}
                                {item.item_unit ? ` ${item.item_unit}` : ''}
                              </Text>
                            </View>
                            <Pressable
                              style={styles.shoppingItemRemove}
                              onPress={(event) => {
                                event.stopPropagation();
                                handleRemoveShoppingItem(item);
                              }}
                              disabled={removingShoppingItemId === item.id}
                            >
                              <Text style={styles.shoppingItemRemoveText}>✕</Text>
                            </Pressable>
                          </View>
                        ))}
                      </View>
                    ))}
                    {!shoppingItems.length && (
                      <Text style={styles.subtleText}>No items yet. Add the first shopping item above.</Text>
                    )}
                  </View>
                )}
              </View>
                </View>
              </TouchableWithoutFeedback>
            </ScrollView>
          ) : (
            <ScrollView
              contentContainerStyle={styles.contentWrap}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
            >
              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Create Shopping List</Text>
                <TextInput
                  style={styles.input}
                  value={shoppingListTitle}
                  onChangeText={setShoppingListTitle}
                  placeholder="List title (optional)"
                />
                {catererChoices.length > 1 && !shoppingEstimateRefId ? (
                  <View style={styles.savedList}>
                    <Text style={styles.subtleText}>Select caterer</Text>
                    <View style={styles.inlineActions}>
                      {catererChoices.map((choice) => (
                        <Pressable
                          key={choice.id}
                          style={[
                            styles.smallButton,
                            shoppingCatererId === choice.id && styles.selectedPill,
                          ]}
                          onPress={() => setShoppingCatererId(choice.id)}
                        >
                          <Text
                            style={[
                              styles.smallButtonText,
                              shoppingCatererId === choice.id && styles.selectedPillText,
                            ]}
                          >
                            {choice.name}
                          </Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ) : null}
                <View style={styles.inlineActions}>
                  <Pressable style={styles.secondaryButton} onPress={() => setShowEstimatePicker(true)}>
                    <Text style={styles.secondaryButtonText}>
                      {selectedEstimateReference
                        ? `Linked Job: #${selectedEstimateReference.estimate_number ?? selectedEstimateReference.id}`
                        : 'Link Job (Optional)'}
                    </Text>
                  </Pressable>
                  {selectedEstimateReference ? (
                    <Pressable
                      style={styles.smallButton}
                      onPress={() => {
                        setShoppingEstimateRefId(null);
                      }}
                    >
                      <Text style={styles.smallButtonText}>Clear Job</Text>
                    </Pressable>
                  ) : null}
                </View>
                <Pressable
                  style={[styles.primaryButton, creatingShoppingList && styles.buttonDisabled]}
                  onPress={handleCreateShoppingList}
                  disabled={creatingShoppingList}
                >
                  {creatingShoppingList ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Create Shopping List</Text>
                  )}
                </Pressable>
              </View>

              <View style={styles.sectionCard}>
                <Text style={styles.sectionTitle}>Open Shopping List</Text>
                {loadingShoppingLists ? (
                  <ActivityIndicator color="#0f766e" />
                ) : (
                  <View style={styles.savedList}>
                    {shoppingLists.map((row) => (
                      <View key={row.id} style={styles.savedCard}>
                        <View style={styles.listRowHeader}>
                          <Pressable style={styles.listRowOpenArea} onPress={() => openShoppingList(row)}>
                            <Text style={styles.savedTitle}>{row.title}</Text>
                          </Pressable>
                          <Pressable
                            style={[
                              styles.listDeleteButton,
                              deletingShoppingListId === row.id && styles.buttonDisabled,
                            ]}
                            onPress={() => handleDeleteShoppingList(row)}
                            disabled={deletingShoppingListId === row.id}
                          >
                            <Text style={styles.listDeleteButtonText}>
                              {deletingShoppingListId === row.id ? '...' : '✕'}
                            </Text>
                          </Pressable>
                        </View>
                        <Pressable style={styles.listRowOpenArea} onPress={() => openShoppingList(row)}>
                          <Text style={styles.subtleText}>
                            {row.item_count} items
                            {row.estimate_label ? ` • ${row.estimate_label}` : ''}
                          </Text>
                          <Text style={styles.subtleText}>{row.caterer_name}</Text>
                        </Pressable>
                      </View>
                    ))}
                    {!shoppingLists.length ? (
                      <Text style={styles.subtleText}>No shopping lists yet.</Text>
                    ) : null}
                  </View>
                )}
              </View>
            </ScrollView>
          )
        )}

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
          visible={!!selectedCatalogItem}
          transparent
          animationType="slide"
          onRequestClose={() => {
            setSelectedCatalogItem(null);
            setCatalogItemUnit('');
          }}
        >
          <View style={styles.modalBackdrop}>
            <TouchableWithoutFeedback onPress={Keyboard.dismiss} accessible={false}>
              <View style={styles.modalCard}>
              <Text style={styles.sectionTitle}>{selectedCatalogItem?.item_name || 'Add Item'}</Text>
              <Text style={styles.subtleText}>Select type, quantity, and unit for this list.</Text>
              {selectedCatalogItem?.type_options?.length ? (
                <View style={styles.savedList}>
                  <Text style={styles.subtleText}>Saved types</Text>
                  <View style={styles.catalogItemWrap}>
                    {selectedCatalogItem.type_options.map((option) => (
                      <Pressable
                        key={option}
                        style={[
                          styles.catalogTypePill,
                          catalogItemType.trim().toLowerCase() === option.toLowerCase() && styles.selectedPill,
                        ]}
                        onPress={() => setCatalogItemType(option)}
                      >
                        <Text
                          style={[
                            styles.catalogTypePillText,
                            catalogItemType.trim().toLowerCase() === option.toLowerCase() &&
                              styles.selectedPillText,
                          ]}
                        >
                          {option}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}
              <TextInput
                style={styles.input}
                value={catalogItemType}
                onChangeText={setCatalogItemType}
                placeholder="Item type (optional)"
              />
              <TextInput
                style={styles.input}
                value={catalogItemQuantity}
                onChangeText={setCatalogItemQuantity}
                keyboardType="decimal-pad"
                inputAccessoryViewID={
                  Platform.OS === 'ios' ? NUMERIC_INPUT_ACCESSORY_ID : undefined
                }
                placeholder="Quantity (default 1)"
              />
              <TextInput
                style={styles.input}
                value={catalogItemUnit}
                onChangeText={setCatalogItemUnit}
                placeholder="Kg, Pieces, Cans"
              />
              <View style={styles.catalogItemWrap}>
                {selectedCatalogUnitOptions.map((option) => {
                  const selected = catalogItemUnit.trim().toLowerCase() === option.toLowerCase();
                  return (
                    <Pressable
                      key={`catalog-unit-${option}`}
                      style={[styles.catalogTypePill, selected && styles.selectedPill]}
                      onPress={() => setCatalogItemUnit(option)}
                    >
                      <Text
                        style={[
                          styles.catalogTypePillText,
                          selected && styles.selectedPillText,
                        ]}
                      >
                        {option}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
              <View style={styles.inlineActions}>
                <Pressable
                  style={[styles.primaryButton, addingShoppingItem && styles.buttonDisabled]}
                  onPress={handleAddCatalogItem}
                  disabled={addingShoppingItem}
                >
                  {addingShoppingItem ? (
                    <ActivityIndicator color="#ffffff" />
                  ) : (
                    <Text style={styles.primaryButtonText}>Add Item</Text>
                  )}
                </Pressable>
                <Pressable
                  style={styles.smallButton}
                  onPress={() => {
                    setSelectedCatalogItem(null);
                    setCatalogItemUnit('');
                  }}
                >
                  <Text style={styles.smallButtonText}>Cancel</Text>
                </Pressable>
              </View>
              </View>
            </TouchableWithoutFeedback>
          </View>
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
        <StatusBar style="dark" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.flexOne}>
        <ScrollView contentContainerStyle={styles.contentWrap}>
          <View style={styles.headerRow}>
            <View style={styles.inlineActions}>
              <Pressable style={styles.smallButton} onPress={() => setSelectedEstimate(null)}>
                <Text style={styles.smallButtonText}>Back</Text>
              </Pressable>
              <Pressable style={styles.smallButton} onPress={handleLogout}>
                <Text style={styles.smallButtonText}>Log Out</Text>
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

          {selectedJobTab === 'expenses' ? (
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

        <View style={styles.bottomTabs}>
          <Pressable
            style={[styles.bottomTabButton, selectedJobTab === 'expenses' && styles.bottomTabButtonActive]}
            onPress={() => setSelectedJobTab('expenses')}
          >
            <Text style={[styles.bottomTabLabel, selectedJobTab === 'expenses' && styles.bottomTabLabelActive]}>
              Expenses
            </Text>
          </Pressable>
          {selectedEstimate.can_manage_staff ? (
            <Pressable
              style={[styles.bottomTabButton, selectedJobTab === 'staff' && styles.bottomTabButtonActive]}
              onPress={() => setSelectedJobTab('staff')}
            >
              <Text style={[styles.bottomTabLabel, selectedJobTab === 'staff' && styles.bottomTabLabelActive]}>
                Staff
              </Text>
            </Pressable>
          ) : null}
        </View>
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
      <StatusBar style="dark" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  flexOne: {
    flex: 1,
  },
  screen: {
    flex: 1,
    backgroundColor: '#eef3ef',
  },
  screenCenter: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: '#eef3ef',
  },
  contentWrap: {
    padding: 16,
    gap: 14,
    paddingBottom: 96,
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
    borderRadius: 16,
    backgroundColor: '#ffffff',
    padding: 14,
    gap: 10,
    shadowColor: '#0f172a',
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0f172a',
  },
  subtleText: {
    color: '#475569',
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
  },
  inlineActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  listHeaderTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
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
  topTabs: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
  },
  topTabButton: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    borderWidth: 1,
    borderColor: '#d1d5db',
  },
  topTabButtonActive: {
    backgroundColor: '#0f766e',
    borderColor: '#0f766e',
  },
  topTabLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0f172a',
  },
  topTabLabelActive: {
    color: '#ffffff',
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
  jobsListWrap: {
    padding: 16,
    gap: 12,
  },
  jobCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 4,
  },
  jobTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#0f172a',
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
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d1d5db',
    backgroundColor: '#f8fafc',
    padding: 10,
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
  bottomTabs: {
    borderTopWidth: 1,
    borderTopColor: '#d1d5db',
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    paddingHorizontal: 10,
    paddingVertical: 8,
    gap: 8,
  },
  bottomTabButton: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
  },
  bottomTabButtonActive: {
    backgroundColor: '#0f766e',
  },
  bottomTabLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0f172a',
  },
  bottomTabLabelActive: {
    color: '#ffffff',
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
