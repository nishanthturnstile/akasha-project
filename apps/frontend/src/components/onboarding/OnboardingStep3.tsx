import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useCompleteOnboarding, useCrops, useSeason, useUpdateField } from '@/lib/queries';
import type { VegetationCycleCreate } from '@/types/api';

const ONBOARDING_SEASON_KEY = 'akasha.onboarding.seasonId';
const ONBOARDING_FIELD_KEY = 'akasha.onboarding.fieldId';

function dateLabel(crop: { seedingTypeId?: number | null } | null): string {
  switch (crop?.seedingTypeId) {
    case 1: return 'Sowing date';
    case 2: return 'Planting date';
    case 3: return 'Planting date';
    case 4: return 'Bud swelling start date';
    case 5: return 'Bud sprouting start date';
    default: return 'Start date';
  }
}

/**
 * Onboarding step 3 – add crop details.
 * Shows crop name dropdown (populated from the /api/crops endpoint) and
 * a date picker constrained to the season's date range.
 */
export default function OnboardingStep3() {
  const navigate = useNavigate();
  const cropsQ = useCrops();
  const completeOnboarding = useCompleteOnboarding();
  const updateField = useUpdateField();

  const seasonId = sessionStorage.getItem(ONBOARDING_SEASON_KEY);
  const seasonQ = useSeason(seasonId);

  const [cropName, setCropName] = useState('');
  const [startDate, setStartDate] = useState('');
  const selectedCrop = cropsQ.data?.find((c) => c.name === cropName) ?? null;
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [dateSynced, setDateSynced] = useState(false);

  if (!dateSynced) {
    if (seasonQ.data?.startDate) {
      setStartDate(seasonQ.data.startDate);
      setDateSynced(true);
    } else if (!seasonQ.isLoading) {
      const y = new Date().getFullYear();
      setStartDate(`${y}-01-01`);
      setDateSynced(true);
    }
  }

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
      const lastFieldId = sessionStorage.getItem(ONBOARDING_FIELD_KEY);
      sessionStorage.removeItem(ONBOARDING_FIELD_KEY);

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
    <div className="hero-pattern flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-bg-light-secondary/45 px-6 py-4 dark:bg-background">
      <StepIndicator currentStep={ 3 } />

      <Card className="gradient-border w-full max-w-md shrink-0">
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
            <label className="text-sm font-medium">{ dateLabel(selectedCrop) }</label>
            <DatePicker
              value={ startDate }
              onChange={ setStartDate }
              placeholder="Select start date"
              className="w-full"
              minDate={ seasonQ.data?.startDate ?? undefined }
              maxDate={ seasonQ.data?.endDate ?? undefined }
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
