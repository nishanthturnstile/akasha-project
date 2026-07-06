import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useCreateSeason, useSeason, useSeasons, useUpdateSeason } from '@/lib/queries';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';

/**
 * Onboarding step 1 – create or edit the first season.
 * If a seasonId already exists in sessionStorage (e.g. when navigating back
 * from step 2), the form loads the saved data and updates it on save.
 */
export default function OnboardingStep1() {
  const navigate = useNavigate();
  const createSeason = useCreateSeason();
  const updateSeason = useUpdateSeason();
  const seasonsQuery = useSeasons();

  const existingSeasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);
  const seasonQuery = useSeason(existingSeasonId);

  const currentYear = new Date().getFullYear();
  const defaultStartDate = `${currentYear}-01-01`;
  const defaultEndDate = `${currentYear}-12-31`;

  const [seasonName, setSeasonName] = useState('');
  const [startDate, setStartDate] = useState(defaultStartDate);
  const [endDate, setEndDate] = useState(defaultEndDate);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [startDateError, setStartDateError] = useState<string | null>(null);
  const [endDateError, setEndDateError] = useState<string | null>(null);
  const [synced, setSynced] = useState(false);

  if (seasonQuery.data && !synced) {
    setSynced(true);
    setSeasonName(seasonQuery.data.name);
    setStartDate(seasonQuery.data.startDate ?? defaultStartDate);
    setEndDate(seasonQuery.data.endDate ?? defaultEndDate);
  }

  const isEditing = !!existingSeasonId;

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
    const trimmed = seasonName.trim();
    if (!trimmed) return;
    const timer = setTimeout(() => {
      if (existingSeasonNames.has(trimmed.toLowerCase())) {
        setNameError('Season name already exists.');
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [seasonName, existingSeasonNames]);

  const canProceed = !!seasonName && !!startDate && !!endDate && !nameError;

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
    <div className="flex h-dvh flex-col items-center overflow-hidden px-6 py-4">
      <StepIndicator currentStep={1} />

      <Card className="w-full max-w-md shrink-0">
        <CardHeader>
          <CardTitle>Let's start with creating your first season</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            It will help you track everything from sowing to harvest.
          </p>
          <label className="text-sm">Season name <span className="text-destructive">*</span></label>
          <input
            placeholder="Season name"
            value={seasonName}
            onChange={(e) => { setSeasonName(e.target.value); setNameError(null); setStartDateError(null); setEndDateError(null); }}
            className="w-full rounded-md border border-border bg-background px-3 py-2"
          />
          {nameError && (
            <p className="text-sm text-destructive">{nameError}</p>
          )}
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-sm">Start date <span className="text-destructive">*</span></label>
              <DatePicker
                value={startDate}
                onChange={(v) => {
                  setStartDate(v);
                  setStartDateError(null);
                  if (endDate && v >= endDate) { setEndDate(''); setEndDateError(null); }
                }}
                placeholder="Start Date"
                className="w-full"
                onOpenChange={(open) => { if (open && !seasonName.trim()) setNameError('Season name is required'); }}
              />
              {startDateError && <p className="text-sm text-destructive mt-1">{startDateError}</p>}
            </div>
            <div className="flex-1">
              <label className="text-sm">End date <span className="text-destructive">*</span></label>
              <DatePicker
                value={endDate}
                onChange={(v) => { setEndDate(v); setEndDateError(null); }}
                placeholder="End Date"
                className="w-full"
                disabled={!startDate}
                minDate={endDateMin}
                onOpenChange={(open) => { if (open && !seasonName.trim()) setNameError('Season name is required'); }}
              />
              {endDateError && <p className="text-sm text-destructive mt-1">{endDateError}</p>}
            </div>
          </div>
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          <Button
            variant="primary"
            disabled={!canProceed || isPending}
            onClick={handleNext}
            className="w-full"
          >
            {isPending ? 'Saving…' : 'Next'}
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
