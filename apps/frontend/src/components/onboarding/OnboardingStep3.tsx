import { useState } from 'react';
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
import { useCompleteOnboarding, useCrops, useUpdateField } from '@/lib/queries';
import type { VegetationCycleCreate } from '@/types/api';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const ONBOARDING_FIELDS_KEY = 'akasha.onboarding.fieldIds';

/**
 * Onboarding step 3 – add crop details.
 * Shows crop name dropdown (populated from the /api/crops endpoint) and
 * auto-filled start date from the season.
 */
export default function OnboardingStep3() {
  const navigate = useNavigate();
  const cropsQ = useCrops();
  const completeOnboarding = useCompleteOnboarding();
  const updateField = useUpdateField();
  const [cropName, setCropName] = useState('');
  const [startDate, setStartDate] = useState('2026-01-01');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const seasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);

  const handleCancel = () => {
    navigate('/onboarding/step2');
  };

  const handleFinish = async () => {
    if (!cropName) {
      setError('Please select a crop');
      return;
    }
    setError(null);
    setSaving(true);
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

      // Save the selected crop as a vegetation cycle for the last field
      if (lastFieldId && seasonId && cropName) {
        const crop = cropsQ.data?.find((c) => c.name === cropName);
        if (crop) {
          const vegPayload: VegetationCycleCreate[] = [{
            seasonId,
            year: new Date().getFullYear(),
            cropType: crop.id,
            sowingDate: startDate || undefined,
          }];
          await updateField.mutateAsync({
            fieldId: lastFieldId,
            payload: { vegetationData: vegPayload },
          });
        }
      }

      navigate(lastFieldId ? `/monitoring/field-analytics/field/${lastFieldId}` : '/');
    } catch (err) {
      setSaving(false);
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
            { cropsQ.isPending ? (
              <div className="h-10 flex items-center text-sm text-muted-foreground px-1">
                Loading crops…
              </div>
            ) : cropsQ.error ? (
              <div className="h-10 flex items-center text-sm text-destructive px-1">
                Failed to load crops
              </div>
            ) : (
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
                  { (cropsQ.data ?? []).map((crop) => (
                    <SelectItem key={ crop.id } value={ crop.name }>{ crop.name }</SelectItem>
                  )) }
                </SelectContent>
              </Select>
            ) }
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Start date</label>
            <input
              type="date"
              value={ startDate }
              onChange={ (e) => setStartDate(e.target.value) }
              className="w-full rounded-md border border-border bg-background px-3 py-2"
            />
          </div>

          { error && <p className="text-sm text-destructive">{ error }</p> }

          <div className="flex justify-between gap-2 pt-2">
            <Button variant="secondary" onClick={ handleCancel }>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={ handleFinish }
              disabled={ !cropName || saving || completeOnboarding.isPending }
            >
              { saving || completeOnboarding.isPending ? 'Finishing…' : 'Finish' }
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
