import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useCreateSeason, usePredefinedSeasons, useSeason, useSeasons, useUpdateSeason } from '@/lib/queries';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const CUSTOM = '__custom__';
const INITIAL = '__initial__';

export default function OnboardingStep1() {
  const navigate = useNavigate();
  const createSeason = useCreateSeason();
  const updateSeason = useUpdateSeason();
  const seasonsQuery = useSeasons();
  const predefinedQ = usePredefinedSeasons();

  const existingSeasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);
  const seasonQuery = useSeason(existingSeasonId);

  const currentYear = new Date().getFullYear();
  const defaultStartDate = `${currentYear}-01-01`;
  const defaultEndDate = `${currentYear}-12-31`;

  const [selectedKey, setSelectedKey] = useState<string>(INITIAL);
  const [seasonName, setSeasonName] = useState('');
  const [customNameDraft, setCustomNameDraft] = useState('');
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(defaultEndDate);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [startDateError, setStartDateError] = useState<string | null>(null);
  const [endDateError, setEndDateError] = useState<string | null>(null);
  const [synced, setSynced] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  const predefinedMap = useMemo(() => {
    const map = new Map<string, NonNullable<typeof predefinedQ.data>[number]>();
    const data = predefinedQ.data;
    if (Array.isArray(data)) {
      for (const s of data) {
        map.set(s.seasonName, s);
      }
    }
    return map;
  }, [predefinedQ]);

  const isEditing = !!existingSeasonId;
  const isCustom = selectedKey === CUSTOM;

  if (seasonQuery.data && !synced) {
    setSynced(true);
    const name = seasonQuery.data.name;
    setSelectedKey(predefinedMap.has(name) ? name : CUSTOM);
    setSeasonName(name);
    setStartDate(seasonQuery.data.startDate ?? defaultStartDate);
    setEndDate(seasonQuery.data.endDate ?? defaultEndDate);
  }

  useEffect(() => {
    if (!isCustom) return;
    const id = setTimeout(() => inputRef.current?.focus(), 100);
    return () => clearTimeout(id);
  }, [isCustom]);

  const endDateMin = useMemo(() => {
    if (!startDate) return undefined;
    const d = new Date(startDate + 'T00:00:00');
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  }, [startDate]);

  const existingSeasonNames = useMemo(() => {
    if (!Array.isArray(seasonsQuery.data)) return new Set<string>();
    return new Set(
      seasonsQuery.data
        .filter((s) => !isEditing || s.id !== existingSeasonId)
        .map((s) => s.name.toLowerCase().trim()),
    );
  }, [seasonsQuery.data, isEditing, existingSeasonId]);

  useEffect(() => {
    if (!isCustom) return;
    const trimmed = seasonName.trim();
    if (!trimmed) return;
    const timer = setTimeout(() => {
      if (existingSeasonNames.has(trimmed.toLowerCase())) {
        setNameError('Season name already exists.');
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [seasonName, existingSeasonNames, isCustom]);

  const handleSelect = (key: string) => {
    if (isCustom && key !== CUSTOM) {
      setCustomNameDraft(seasonName);
    }
    setSelectedKey(key);
    setNameError(null);
    setStartDateError(null);
    setEndDateError(null);
    if (key === CUSTOM) {
      setSeasonName(customNameDraft);
      const y = new Date().getFullYear();
      setStartDate(`${y}-01-01`);
      setEndDate(`${y}-12-31`);
    } else if (key !== INITIAL) {
      const p = predefinedMap.get(key);
      setSeasonName(key);
      if (p?.periodStartDate) setStartDate(p.periodStartDate);
      if (p?.periodEndDate) setEndDate(p.periodEndDate);
    }
    setDropdownOpen(false);

    if (key === CUSTOM) {
      // Radix Select restores focus to the hidden trigger after closing;
      // nest rAFs to yield past Radix's focus management.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          inputRef.current?.focus();
        });
      });
    }
  };

  const canProceed = !!seasonName && !!startDate && !!endDate && !nameError && selectedKey !== INITIAL;

  const isPending = createSeason.isPending || updateSeason.isPending;

  const handleNext = async () => {
    let hasError = false;
    if (!seasonName.trim()) { setNameError('Season name is required'); hasError = true; }
    if (!startDate) { setStartDateError('Start date is required'); hasError = true; }
    if (!endDate) { setEndDateError('End date is required'); hasError = true; }
    if (hasError || !canProceed) return;
    setError(null);
    try {
      if (isEditing) {
        await updateSeason.mutateAsync({
          seasonId: existingSeasonId,
          payload: {
            name: seasonName.trim(),
            startDate: startDate || null,
            endDate: endDate || null,
          },
        });
      } else {
        const season = await createSeason.mutateAsync({
          name: seasonName.trim(),
          startDate: startDate || null,
          endDate: endDate || null,
        });
        sessionStorage.setItem(ONBOARDING_SEASON_KEY, season.id);
      }
      navigate('/onboarding/step2');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save season';
      setError(message);
    }
  };

  return (
    <div className="hero-pattern flex h-dvh flex-col items-center overflow-hidden bg-bg-light-secondary/45 px-6 py-4 dark:bg-background">
      <StepIndicator currentStep={1} />

      <Card className="gradient-border w-full max-w-md shrink-0">
        <CardHeader>
          <CardTitle>Let's start with creating your first season</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            It will help you track everything from sowing to harvest.
          </p>

          <div className="space-y-2">
            <label className="text-sm font-medium">Season name <span className="text-destructive">*</span></label>

            <div className="relative">
              <Select value={ selectedKey } onValueChange={ handleSelect } open={ dropdownOpen } onOpenChange={ setDropdownOpen }>
                <SelectTrigger className="sr-only" />
                <SelectContent>
                  { Array.isArray(predefinedQ.data) && predefinedQ.data.map((s) => (
                    <SelectItem key={ s.id } value={ s.seasonName }>{ s.seasonName }</SelectItem>
                  )) }
                  <SelectItem value={ CUSTOM }>Custom</SelectItem>
                </SelectContent>
              </Select>

              { isCustom ? (
                <div className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2">
                  <input
                    ref={ inputRef }
                    value={ seasonName }
                    autoFocus
                    maxLength={15}
                    onChange={ (e) => { setSeasonName(e.target.value); setNameError(null); setStartDateError(null); setEndDateError(null); } }
                    placeholder="Enter season name"
                    className="flex-1 bg-transparent outline-none text-sm"
                  />
                  <button
                    type="button"
                    onClick={ () => setDropdownOpen(true) }
                    className="flex cursor-pointer items-center"
                  >
                    <ChevronDown className="size-4 text-muted-foreground" />
                  </button>
                </div>
              ) : (
                <div
                  className="flex h-10 w-full cursor-pointer items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background hover:bg-accent/40 focus-within:outline-none focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
                  onClick={ () => setDropdownOpen(true) }
                >
                  <span className={ selectedKey === INITIAL ? 'text-muted-foreground' : '' }>
                    { selectedKey === INITIAL ? 'Choose season' : selectedKey }
                  </span>
                  <ChevronDown className="size-4 text-muted-foreground" />
                </div>
              ) }
            </div>

            { nameError && (
              <p className="text-sm text-destructive">{ nameError }</p>
            ) }
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-sm">Start date <span className="text-destructive">*</span></label>
              <DatePicker
                value={ startDate }
                disabled={ !isCustom }
                onChange={ (v) => {
                  setStartDate(v);
                  setStartDateError(null);
                  if (endDate && v >= endDate) { setEndDate(''); setEndDateError(null); }
                } }
                placeholder="Start Date"
                className="w-full"
              />
              { startDateError && <p className="text-sm text-destructive mt-1">{ startDateError }</p> }
            </div>
            <div className="flex-1">
              <label className="text-sm">End date <span className="text-destructive">*</span></label>
              <DatePicker
                value={ endDate }
                disabled={ !isCustom || !startDate }
                onChange={ (v) => { setEndDate(v); setEndDateError(null); } }
                placeholder="End Date"
                className="w-full"
                minDate={ endDateMin }
              />
              { endDateError && <p className="text-sm text-destructive mt-1">{ endDateError }</p> }
            </div>
          </div>

          { error && (
            <p className="text-sm text-destructive">{ error }</p>
          ) }
          <Button
            variant="primary"
            disabled={ !canProceed || isPending }
            onClick={ handleNext }
            className="w-full"
          >
            { isPending ? 'Saving…' : 'Next' }
          </Button>
        </CardContent>
      </Card>
      <img
        src="/images/onboarding1.png"
        alt="Create season illustration"
        className="mt-auto w-full shrink-0"
      />
    </div>
  );
}
