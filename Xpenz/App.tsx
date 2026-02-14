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
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
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
  caterer_name: string;
  currency: string;
  grand_total: string;
  expense_count: number;
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
  voiceUri?: string;
  voiceDurationSeconds?: number;
  expenseText: string;
  expenseAmount: string;
  noteText: string;
};

const TOKEN_KEY = 'xpenz_token';
const BASE_URL_KEY = 'xpenz_base_url';
const DEFAULT_BASE_URL = 'https://cater-base-pro.herokuapp.com';

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
  const [estimates, setEstimates] = useState<EstimateRow[]>([]);
  const [selectedEstimate, setSelectedEstimate] = useState<EstimateRow | null>(null);
  const [savedEntries, setSavedEntries] = useState<SavedEntry[]>([]);

  const [drafts, setDrafts] = useState<ExpenseDraft[]>([]);
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
        throw new Error(payload.error || `Request failed (${response.status})`);
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
          await loadEstimates(savedToken, savedBase);
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
  }, [loadEstimates]);

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
      await loadEstimates(payload.token, cleanBase);
      setPassword('');
    } catch (error) {
      Alert.alert('Login error', error instanceof Error ? error.message : 'Unable to log in.');
    } finally {
      setLoggingIn(false);
    }
  }, [apiBaseUrl, loadEstimates, password, username]);

  const handleLogout = useCallback(async () => {
    try {
      await Promise.all([
        SecureStore.deleteItemAsync(TOKEN_KEY),
        SecureStore.deleteItemAsync(BASE_URL_KEY),
      ]);
    } finally {
      setToken('');
      setSelectedEstimate(null);
      setEstimates([]);
      setSavedEntries([]);
      setDrafts([]);
    }
  }, []);

  const handleSelectEstimate = useCallback(
    async (estimate: EstimateRow) => {
      setSelectedEstimate(estimate);
      setDrafts([]);
      try {
        await loadEntries(estimate.id);
      } catch (error) {
        Alert.alert(
          'Load error',
          error instanceof Error ? error.message : 'Unable to load estimate entries.',
        );
      }
    },
    [loadEntries],
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

    const { granted } = await requestRecordingPermissionsAsync();
    if (!granted) {
      Alert.alert('Microphone permission needed', 'Allow microphone access to record voice notes.');
      return;
    }

    try {
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecordingPhotoUri(pickerResult.assets[0].uri);
      setRecordingStartedAt(Date.now());
    } catch (error) {
      Alert.alert(
        'Recording error',
        error instanceof Error ? error.message : 'Unable to start recording.',
      );
    }
  }, [isRecording, recorder]);

  const stopRecordingAndCreateDraft = useCallback(async () => {
    if (!recordingPhotoUri) {
      return;
    }

    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });

      const voiceUri = recorder.uri;
      if (!voiceUri) {
        throw new Error('Recording finished but no audio file was found.');
      }

      const fallbackSeconds = recordingStartedAt
        ? Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000))
        : 1;
      const durationSeconds = recorderState.durationMillis
        ? Math.max(1, Math.round(recorderState.durationMillis / 1000))
        : fallbackSeconds;

      const nextDraft: ExpenseDraft = {
        localId: localId(),
        manualOnly: false,
        receiptUri: recordingPhotoUri,
        voiceUri,
        voiceDurationSeconds: durationSeconds,
        expenseText: '',
        expenseAmount: '',
        noteText: '',
      };

      setDrafts((prev) => [nextDraft, ...prev]);
      setRecordingPhotoUri(null);
      setRecordingStartedAt(null);
    } catch (error) {
      Alert.alert(
        'Stop recording error',
        error instanceof Error ? error.message : 'Unable to stop recording.',
      );
    }
  }, [recorder, recorderState.durationMillis, recordingPhotoUri, recordingStartedAt]);

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

        if (!draft.manualOnly && (!draft.receiptUri || !draft.voiceUri)) {
          throw new Error(`Draft ${index + 1} is missing receipt or voice note.`);
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
        if (!draft.manualOnly && draft.receiptUri && draft.voiceUri) {
          formData.append('receipt_image', {
            uri: draft.receiptUri,
            name: `receipt-${draft.localId}.jpg`,
            type: 'image/jpeg',
          } as unknown as Blob);
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
            <Text style={styles.appTitle}>Xpenz</Text>
            <Text style={styles.subtleText}>Internal expense capture for estimates</Text>

            <Text style={styles.label}>API Base URL</Text>
            <TextInput
              style={styles.input}
              value={apiBaseUrl}
              onChangeText={setApiBaseUrl}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="https://cater-base-pro.herokuapp.com"
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
        <View style={styles.headerRow}>
          <Text style={styles.sectionTitle}>Select Job</Text>
          <View style={styles.inlineActions}>
            <Pressable style={styles.smallButton} onPress={() => loadEstimates()}>
              <Text style={styles.smallButtonText}>Refresh</Text>
            </Pressable>
            <Pressable style={styles.smallButton} onPress={handleLogout}>
              <Text style={styles.smallButtonText}>Log Out</Text>
            </Pressable>
          </View>
        </View>

        {loadingJobs ? (
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
                  {estimate.currency} {estimate.grand_total} • {estimate.expense_count} saved entries
                </Text>
              </Pressable>
            ))}
            {!estimates.length && <Text style={styles.subtleText}>No estimates found for this account.</Text>}
          </ScrollView>
        )}
        <StatusBar style="dark" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
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
        </View>

        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Add Expenses</Text>
          <Text style={styles.subtleText}>
            Capture receipt + voice note, then type the expense line under that item. Use + for manual entries.
          </Text>
          <View style={styles.inlineActions}>
            <Pressable style={styles.primaryButton} onPress={captureReceiptAndVoice}>
              <Text style={styles.primaryButtonText}>Receipt + Voice</Text>
            </Pressable>
            <Pressable style={styles.secondaryButton} onPress={addManualDraft}>
              <Text style={styles.secondaryButtonText}>+ Manual Expense</Text>
            </Pressable>
          </View>

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

              <TextInput
                style={styles.input}
                value={draft.expenseText}
                onChangeText={(value) => updateDraft(draft.localId, { expenseText: value })}
                placeholder="Expense line (e.g. Produce market)"
              />
              <TextInput
                style={styles.input}
                value={draft.expenseAmount}
                onChangeText={(value) => updateDraft(draft.localId, { expenseAmount: value })}
                keyboardType="decimal-pad"
                placeholder="Expense amount"
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
            style={[styles.primaryButton, (!drafts.length || uploading) && styles.buttonDisabled]}
            onPress={uploadDrafts}
            disabled={!drafts.length || uploading}
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
                    {entry.expense_amount ? `$${entry.expense_amount}` : 'No amount'} •{' '}
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
      </ScrollView>
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
  inlineActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
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
  savedTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0f172a',
  },
});
