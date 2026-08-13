String retentionValue(String branchName, String value) {
  def policies = [
    feature: [buildDays: '14', buildCount: '20', artifactDays: '7', artifactCount: '10'],
    main: [buildDays: '90', buildCount: '50', artifactDays: '30', artifactCount: '20'],
    release: [buildDays: '365', buildCount: '20', artifactDays: '180', artifactCount: '20'],
    nightly: [buildDays: '90', buildCount: '60', artifactDays: '30', artifactCount: '30'],
  ]

  def policy = branchName == 'main'
    ? policies.main
    : branchName == 'nightly' || branchName?.startsWith('nightly/')
      ? policies.nightly
      : branchName == 'release' || branchName?.startsWith('release/')
        ? policies.release
        : policies.feature

  return policy[value]
}

pipeline {
  agent any

  options {
    skipDefaultCheckout(true)
    timestamps()
    timeout(time: 45, unit: 'MINUTES')
    disableConcurrentBuilds(abortPrevious: true)
    buildDiscarder(logRotator(
      numToKeepStr: retentionValue(env.BRANCH_NAME, 'buildCount'),
      daysToKeepStr: retentionValue(env.BRANCH_NAME, 'buildDays'),
      artifactNumToKeepStr: retentionValue(env.BRANCH_NAME, 'artifactCount'),
      artifactDaysToKeepStr: retentionValue(env.BRANCH_NAME, 'artifactDays'),
    ))
  }

  environment {
    COMPOSE_DOCKER_CLI_BUILD = '1'
    E2E_FRONTEND_PORT = '0'
    SUPABASE_CLI_VERSION = '2.112.0'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.REVISION = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.SHORT_REVISION = env.REVISION.take(12)
          env.BACKEND_IMAGE = "valuator-backend:${env.REVISION}"
          env.FRONTEND_IMAGE = "valuator-frontend:${env.REVISION}"
          env.E2E_IMAGE = "valuator-e2e:${env.REVISION}"
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.SHORT_REVISION}"
        }
      }
    }

    stage('PR Validation Policy') {
      when { not { branch 'main' } }
      steps {
        echo 'Full pull-request regression is owned by GitHub Actions; Jenkins runs the full pipeline on main only.'
      }
    }

    stage('Preflight') {
      when { branch 'main' }
      steps {
        sh '''
          set -eu
          docker version
          docker compose version
          node --version
          npx --version
          python3 --version
          python3 -m py_compile scripts/vercel/manage.py scripts/supabase/apply-production.py
          python3 -m unittest discover -s scripts/tests -p 'test_*.py'
          bash -n scripts/jenkins/deploy-vercel.sh
          docker compose --env-file ops/ci.env -f docker-compose.yml config --quiet
          docker compose --env-file ops/ci.env -f docker-compose.e2e.yml config --quiet
          mkdir -p ci-artifacts
          docker run --rm -v "$WORKSPACE/ci-artifacts:/artifacts" alpine \
            rm -rf /artifacts/backend /artifacts/supabase /artifacts/allure-results \
              /artifacts/allure-combined-results /artifacts/playwright
          mkdir -p ci-artifacts/backend ci-artifacts/supabase ci-artifacts/allure-results \
            ci-artifacts/allure-combined-results ci-artifacts/playwright
        '''
      }
    }

    stage('Quality Gates') {
      when { branch 'main' }
      parallel {
        stage('Backend Tests') {
          steps {
            sh '''
              set -eu
              mkdir -p ci-artifacts/backend
              docker build --target test -t "valuator-backend-test:${REVISION}" Back-End
              docker run --rm --env-file ops/ci.env \
                -v "$WORKSPACE/ci-artifacts/backend:/reports" \
                "valuator-backend-test:${REVISION}" \
                python -m pytest tests \
                  --ignore=tests/test_supabase_integration.py \
                  --junitxml=/reports/backend-junit.xml \
                  --alluredir=/reports/allure-results \
                  --allure-no-capture
            '''
          }
        }

        stage('Frontend Lint') {
          steps {
            sh 'docker build --target lint -t "valuator-frontend-lint:${REVISION}" Front-End'
          }
        }

        stage('Performance Harness Validation') {
          steps {
            sh '''
              set -eu
              PERF_POSTGRES_DSN=postgresql://placeholder@127.0.0.1:56322/postgres \
                docker compose -f docker-compose-perf.yml config --quiet
              for script in k6-tests/tests/*.js; do
                docker run --rm \
                  -v "$WORKSPACE/k6-tests:/scripts:ro" \
                  grafana/k6:2.1.0 \
                  inspect "/scripts/tests/$(basename "$script")" >/dev/null
              done
              jq empty grafana/dashboards/valuator-custom-dashboard.json
              bash -n run_all_perf_tests.sh scripts/performance/manage-isolated-supabase.sh
            '''
          }
        }
      }
    }

    stage('Supabase Schema and RLS') {
      when { branch 'main' }
      steps {
        sh '''
          set -eu
          export SUPABASE_TEST_IMAGE="valuator-backend-test:${REVISION}"
          scripts/ci/run-supabase-integration.sh
        '''
      }
    }

    stage('Source and Dependency Security') {
      when { branch 'main' }
      steps {
        sh '''
          set -eu
          docker run --rm "valuator-backend-test:${REVISION}" bandit -r app -q -ll -ii
          docker run --rm "valuator-backend-test:${REVISION}" pip-audit -r requirements.txt
          npm --prefix Front-End audit --omit=dev --audit-level=high
        '''
      }
    }

    stage('Build Images') {
      when { branch 'main' }
      parallel {
        stage('Backend Image') {
          steps {
            sh 'docker build --target runtime -t "$BACKEND_IMAGE" Back-End'
          }
        }
        stage('Frontend Image') {
          steps {
            sh '''
              docker build --target runner \
                --build-arg API_BASE_URL=http://backend:8000 \
                --build-arg APP_REVISION="$REVISION" \
                --build-arg APP_ENV=production \
                -t "$FRONTEND_IMAGE" Front-End
            '''
          }
        }
        stage('Playwright Image') {
          steps {
            sh 'docker build -f Front-End/Dockerfile.e2e -t "$E2E_IMAGE" Front-End'
          }
        }
      }
    }

    stage('Runtime Security Scan') {
      when { branch 'main' }
      steps {
        sh '''
          set -eu
          mkdir -p ci-artifacts/security trivy-cache
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v "$WORKSPACE/trivy-cache:/root/.cache/trivy" \
            -v "$WORKSPACE/ci-artifacts/security:/reports" \
            aquasec/trivy:0.67.2 image --scanners vuln --skip-version-check --ignore-unfixed \
              --severity HIGH,CRITICAL --exit-code 1 "$BACKEND_IMAGE"
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v "$WORKSPACE/trivy-cache:/root/.cache/trivy" \
            -v "$WORKSPACE/ci-artifacts/security:/reports" \
            aquasec/trivy:0.67.2 image --scanners vuln --skip-version-check --ignore-unfixed \
              --severity HIGH,CRITICAL --exit-code 1 "$FRONTEND_IMAGE"
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v "$WORKSPACE/trivy-cache:/root/.cache/trivy" \
            -v "$WORKSPACE/ci-artifacts/security:/reports" \
            aquasec/trivy:0.67.2 image --format cyclonedx \
              --output /reports/backend-sbom.cdx.json "$BACKEND_IMAGE"
          docker run --rm \
            -v /var/run/docker.sock:/var/run/docker.sock \
            -v "$WORKSPACE/trivy-cache:/root/.cache/trivy" \
            -v "$WORKSPACE/ci-artifacts/security:/reports" \
            aquasec/trivy:0.67.2 image --format cyclonedx \
              --output /reports/frontend-sbom.cdx.json "$FRONTEND_IMAGE"
          docker run --rm -v "$WORKSPACE:/repo:ro" \
            zricethezav/gitleaks:v8.28.0 \
            detect --source=/repo --config=/repo/.gitleaks.toml --redact --no-banner
          docker run --rm \
            -v "$WORKSPACE:/repo:ro" \
            -v "$WORKSPACE/trivy-cache:/root/.cache/trivy" \
            aquasec/trivy:0.67.2 config --skip-version-check \
              --skip-files /repo/Front-End/Dockerfile.e2e \
              --severity HIGH,CRITICAL --exit-code 1 /repo
        '''
      }
    }

    stage('Reclaim Disk Space Before E2E') {
      when { branch 'main' }
      // By this point the job has built five Docker images (backend
      // test/runtime, frontend lint/runner, e2e) plus their BuildKit layer
      // cache. The test/lint images are single-use and already consumed;
      // the layer cache is typically the largest consumer. Without this,
      // the E2E docker compose stage (the most disk-heavy stage) can fail
      // with "No space left on device" independent of any test outcome.
      steps {
        sh '''
          set -eu
          docker rmi "valuator-backend-test:${REVISION}" "valuator-frontend-lint:${REVISION}" 2>/dev/null || true
          docker builder prune -af
          df -h /
        '''
      }
    }

    stage('Deterministic VALUATOR E2E') {
      when { branch 'main' }
      steps {
        script {
          try {
            sh '''
              set -eu
              mkdir -p ci-artifacts/playwright ci-artifacts/allure-results
              export E2E_PROJECT="e2e-$(echo ${JOB_NAME} | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')-${BUILD_NUMBER}"
              export CI_BRANCH="${BRANCH_NAME}"
              export CI_COMMIT="${REVISION}"
              export FRONTEND_IMAGE E2E_IMAGE
              docker compose --env-file ops/ci.env -p "$E2E_PROJECT" -f docker-compose.e2e.yml \
                up --abort-on-container-exit --exit-code-from e2e
              node scripts/ci/validate-allure-results.mjs
            '''
          } finally {
            sh '''
              export E2E_PROJECT="e2e-$(echo ${JOB_NAME} | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')-${BUILD_NUMBER}"
              export FRONTEND_IMAGE E2E_IMAGE
              docker compose --env-file ops/ci.env -p "$E2E_PROJECT" -f docker-compose.e2e.yml \
                logs --no-color > ci-artifacts/playwright/compose.log 2>&1 || true
            '''
          }
        }
      }
    }

    stage('Migrate Staging Database') {
      when { branch 'main' }
      environment {
        SUPABASE_STAGING_MODE = 'local'
        VALUATOR_RUNTIME_ENV = credentials('valuator-staging-env')
      }
      steps {
        sh 'scripts/jenkins/push-supabase-migrations.sh'
      }
    }

    stage('Deploy Staging') {
      when {
        allOf {
          branch 'main'
          expression { currentBuild.currentResult == 'SUCCESS' }
        }
      }
      environment {
        VALUATOR_RUNTIME_ENV = credentials('valuator-staging-env')
        FRONTEND_PORT = '3100'
        BACKEND_PORT = '8100'
        STAGING_PROJECT_NAME = 'valuator-staging'
        SUPABASE_STAGING_MODE = 'local'
      }
      steps {
        sh 'scripts/jenkins/deploy-staging.sh'
      }
    }

    stage('Deploy Vercel Production') {
      when {
        allOf {
          branch 'main'
          expression { currentBuild.currentResult == 'SUCCESS' }
        }
      }
      environment {
        VERCEL_TOKEN = credentials('vercel-api-token')
        VALUATOR_PRODUCTION_ENV = credentials('valuator-production-env')
      }
      steps {
        sh 'scripts/jenkins/deploy-vercel.sh'
      }
    }
  }

  post {
    always {
      sh '''
        docker run --rm -v "$WORKSPACE/ci-artifacts:/artifacts" alpine chown -R $(id -u):$(id -g) /artifacts || true
      '''
      junit allowEmptyResults: true, testResults: 'ci-artifacts/**/*junit.xml'
      // Archive the three original result trees. The combined directory is a
      // transient publication input and must not duplicate the raw artifacts.
      archiveArtifacts allowEmptyArchive: true, artifacts: 'ci-artifacts/**/*', excludes: 'ci-artifacts/allure-combined-results/**', fingerprint: true
      catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
        sh 'node scripts/ci/assemble-allure-results.mjs'
      }
      allure includeProperties: false, commandline: 'allure-2.32.0', jdk: '', results: [[path: 'ci-artifacts/allure-combined-results']]
      sh '''
        E2E_PROJECT="e2e-$(echo ${JOB_NAME} | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')-${BUILD_NUMBER}"
        export FRONTEND_IMAGE="${FRONTEND_IMAGE:-unused}" E2E_IMAGE="${E2E_IMAGE:-unused}"
        docker compose --env-file ops/ci.env -p "$E2E_PROJECT" -f docker-compose.e2e.yml down --volumes --remove-orphans || true
      '''
    }
  }
}
