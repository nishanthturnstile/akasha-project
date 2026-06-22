import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useCompleteOnboarding, useSeasons } from '@/lib/queries';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const ONBOARDING_FIELDS_KEY = 'akasha.onboarding.fieldIds';

const CROP_OPTIONS = [
  'Wheat',
  'Rice',
  'Corn',
  'Soybean',
  'Barley',
  'Cotton',
  'Sugarcane',
  'Potato',
  'Tomato',
  'Sunflower',
];

/**
 * Onboarding step 3 – add crop details.
 * Shows crop name dropdown and auto-filled start date from the season.
 */
export default function OnboardingStep3() {
  const navigate = useNavigate();
  const seasonsQ = useSeasons();
  const completeOnboarding = useCompleteOnboarding();
  const [cropName, setCropName] = useState('');
  const [error, setError] = useState<string | null>(null);

  const seasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);

  const seasonStartDate = useMemo(() => {
    if (seasonsQ.data && seasonId) {
      const season = seasonsQ.data.find((s) => s.id === seasonId);
      return season?.startDate ?? null;
    }
    return null;
  }, [seasonsQ.data, seasonId]);

  const handleCancel = () => {
    navigate('/onboarding/step2');
  };

  const handleFinish = async () => {
    if (!cropName) {
      setError('Please select a crop');
      return;
    }
    setError(null);
    try {
      await completeOnboarding.mutateAsync();
      // Clear onboarding session keys
      sessionStorage.removeItem(ONBOARDING_SEASON_KEY);
      const storedIds = (() => {
        try {
          return JSON.parse(sessionStorage.getItem(ONBOARDING_FIELDS_KEY) ?? '[]') as string[];
        } catch {
          return [];
        }
      })();
      const lastFieldId = storedIds[storedIds.length - 1];
      sessionStorage.removeItem(ONBOARDING_FIELDS_KEY);
      navigate(lastFieldId ? `/monitoring/field-analytics/field/${lastFieldId}` : '/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete onboarding');
    }
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center overflow-hidden px-6 py-4">
      <StepIndicator currentStep={ 3 } />

      <Card className="w-full max-w-md shrink-0">
        <CardHeader>
          <CardTitle>Add crop</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Select the crop you are growing this season.
          </p>

          <div className="space-y-2">
            <label className="text-sm font-medium">Crop name</label>
            <Select
              value={ cropName }
              onValueChange={ (value) => {
                setCropName(value);
                setError(null);
              } }
            >
              <SelectTrigger>
                <SelectValue placeholder="Select a crop" />
              </SelectTrigger>
              <SelectContent>
                { CROP_OPTIONS.map((crop) => (
                  <SelectItem key={ crop } value={ crop }>{ crop }</SelectItem>
                )) }
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Start date</label>
            <input
              type="date"
              value={ seasonStartDate ?? '' }
              readOnly
              className="w-full rounded-md border border-border bg-muted px-3 py-2 text-muted-foreground cursor-not-allowed"
            />
            <p className="text-xs text-muted-foreground">
              Auto-filled from the selected season
            </p>
          </div>

          { error && <p className="text-sm text-destructive">{ error }</p> }

          <div className="flex justify-between gap-2 pt-2">
            <Button variant="secondary" onClick={ handleCancel }>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={ handleFinish }
              disabled={ !cropName || completeOnboarding.isPending }
            >
              { completeOnboarding.isPending ? 'Finishing…' : 'Finish' }
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
