import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StepIndicator } from '@/components/onboarding/StepIndicator';
import { useFields } from '@/lib/queries';

const ONBOARDING_FIELDS_KEY = 'akasha.onboarding.fieldIds';

/**
 * Onboarding step 2 – add multiple fields linked to the created season.
 * Reads seasonId from sessionStorage and passes it when creating fields.
 */
export default function OnboardingStep2() {
  const navigate = useNavigate();
  const fieldsQ = useFields();

  const savedFieldIds = (() => {
    try {
      const raw = sessionStorage.getItem(ONBOARDING_FIELDS_KEY);
      return raw ? (JSON.parse(raw) as string[]) : [];
    } catch {
      return [];
    }
  })();

  const savedFields =
    fieldsQ.data?.filter((f) => savedFieldIds.includes(f.id)) ?? [];

  const handleAddField = () => navigate('/onboarding/field-create');
  const handleBack = () => navigate('/onboarding/step1');
  const handleNext = () => navigate('/onboarding/step3');

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center overflow-hidden px-6 py-4">
      <StepIndicator currentStep={2} />

      <Card className="w-full max-w-md shrink-0">
        <CardHeader>
          <CardTitle>Let's add your fields</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Draw one or more fields. All fields will be linked to the season you just created.
          </p>

          {savedFields.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Saved fields ({savedFields.length})</p>
              {savedFields.map((field) => (
                <div
                  key={field.id}
                  className="flex items-center justify-between rounded-md border border-border bg-card/50 px-3 py-2"
                >
                  <span className="text-sm">{field.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {field.areaHa != null ? `${field.areaHa.toFixed(2)} ha` : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex justify-between gap-2">
            <Button variant="secondary" onClick={handleBack}>
              Back
            </Button>
            <Button variant="primary" onClick={handleAddField}>
              Add field
            </Button>
          </div>

          {savedFields.length > 0 && (
            <Button variant="primary" onClick={handleNext} className="w-full">
              Next
            </Button>
          )}
        </CardContent>
      </Card>
      <img
        src="/images/onboardig2.png"
        alt="Add field illustration"
        className="mt-2 max-h-[25vh] w-auto object-contain shrink-0"
      />
    </div>
  );
}
