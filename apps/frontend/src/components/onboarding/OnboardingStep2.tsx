import { useNavigate } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StepIndicator } from '@/components/onboarding/StepIndicator';

const ONBOARDING_FIELD_KEY = 'akasha.onboarding.fieldId';

/**
 * Onboarding step 2 – draw a single field linked to the created season.
 * If no field exists yet, user draws one. If a field already exists,
 * user can edit it or proceed to the next step.
 */
export default function OnboardingStep2() {
  const navigate = useNavigate();

  const savedFieldId = sessionStorage.getItem(ONBOARDING_FIELD_KEY);

  const handleDrawField = () => navigate('/onboarding/field-create');
  const handleEditField = () => navigate(`/onboarding/field-create?fieldId=${encodeURIComponent(savedFieldId!)}`);
  const handleBack = () => navigate('/onboarding/step1');
  const handleNext = () => navigate('/onboarding/step3');

  return (
    <div className="flex h-dvh flex-col items-center overflow-hidden px-6 py-4">
      <StepIndicator currentStep={2} />

      <Card className="w-full max-w-md shrink-0">
        <CardHeader>
          <CardTitle>Let's add your field</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Draw your field boundary. It will be linked to the season you just created.
          </p>

          <div className="flex justify-between gap-2">
            <Button variant="secondary" onClick={handleBack}>
              Back
            </Button>
            {savedFieldId ? (
              <Button variant="primary" onClick={handleEditField}>
                Edit field
              </Button>
            ) : (
              <Button variant="primary" onClick={handleDrawField}>
                Draw field
              </Button>
            )}
          </div>

          {savedFieldId && (
            <Button variant="primary" onClick={handleNext} className="w-full">
              Next
            </Button>
          )}
        </CardContent>
      </Card>
      <img
        src="/images/onboardig2.png"
        alt="Add field illustration"
        className="mt-auto w-full shrink-0"
      />
    </div>
  );
}
