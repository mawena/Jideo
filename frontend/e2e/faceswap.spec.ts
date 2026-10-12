import { expect, test } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url))

test('swap photo de bout en bout', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('source-input').setInputFiles(fixture('source.png'))
  // Première détection après un démarrage : les modèles se chargent à la demande.
  await expect(page.getByTestId('source-face-0')).toHaveAttribute('aria-pressed', 'true', { timeout: 30_000 })
  await page.getByTestId('target-input').setInputFiles(fixture('group.jpg'))
  await expect(page.getByTestId('target-face-0')).toBeVisible()

  await page.getByTestId('launch').click()

  const job = page.getByTestId('job').first()
  await expect(job).toContainText('Photo')
  await expect(job).toContainText('Terminé', { timeout: 60_000 })
  await job.getByRole('button', { name: 'Voir' }).click()
  await expect(page.getByTestId('before-after')).toBeVisible()
})

test('aperçu sur une image de vidéo', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('source-input').setInputFiles(fixture('source.png'))
  await expect(page.getByTestId('source-face-0')).toHaveAttribute('aria-pressed', 'true')
  await page.getByTestId('target-input').setInputFiles(fixture('clip.mp4'))
  await expect(page.getByTestId('target-face-0')).toBeVisible()
  await page.getByTestId('pick-frame').click()
  await expect(page.getByTestId('target-face-0')).toBeVisible()

  await page.getByTestId('preview').click()

  const job = page.getByTestId('job').first()
  await expect(job).toContainText('Aperçu')
  await expect(job).toContainText('Terminé', { timeout: 60_000 })
})
