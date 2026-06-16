import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useCreateSeason } from '@/lib/queries';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';

/**
 * Onboarding step 1 – create first season.
 * Calls the Create Season API and stores the returned seasonId in sessionStorage.
 */
export default function OnboardingStep1() {
  const navigate = useNavigate();
  const createSeason = useCreateSeason();
  const [seasonName, setSeasonName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [error, setError] = useState<string | null>(null);

  const canProceed = !!seasonName && !!startDate && !!endDate;

  const handleNext = async () => {
    if (!canProceed) return;
    setError(null);
    try {
      const season = await createSeason.mutateAsync({
        name: seasonName.trim(),
        startDate: startDate || null,
        endDate: endDate || null,
      });
      sessionStorage.setItem(ONBOARDING_SEASON_KEY, season.id);
      navigate('/onboarding/step2');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create season';
      setError(message);
    }
  };

  return (
    <div className="flex flex-col items-center p-6">
      <StepIndicator currentStep={1} />

      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Let's start with creating your first season</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            It will help you track everything from sowing to harvest.
          </p>
          <input
            placeholder="Season name"
            value={seasonName}
            onChange={(e) => setSeasonName(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-3 py-2"
          />
          <div className="flex gap-2">
            <DatePicker
              value={startDate}
              onChange={setStartDate}
              placeholder="Start Date"
              className="w-full"
            />
            <DatePicker
              value={endDate}
              onChange={setEndDate}
              placeholder="End Date"
              className="w-full"
            />
          </div>
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
          <Button
            variant="primary"
            disabled={!canProceed || createSeason.isPending}
            onClick={handleNext}
            className="w-full"
          >
            {createSeason.isPending ? 'Creating…' : 'Next'}
          </Button>
        </CardContent>
      </Card>
      <img
        src="/images/onboarding1.png"
        alt="Create season illustration"
        className="mt-4 max-w-full h-auto"
      />
    </div>
  );
}
