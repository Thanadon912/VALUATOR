import com.cloudbees.plugins.credentials.CredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.common.StandardUsernamePasswordCredentials
import com.cloudbees.plugins.credentials.domains.Domain
import com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl
import jenkins.model.Jenkins
import org.jenkinsci.plugins.plaincredentials.StringCredentials

def sourceId = "01"
def targetId = "valuator-github-scan"

def existing = CredentialsProvider.lookupCredentials(
  StandardUsernamePasswordCredentials.class,
  Jenkins.get()
).find { credential -> credential.id == targetId }

if (existing != null) {
  println("GitHub scan credential is ready: ${targetId}")
  return
}

def source = CredentialsProvider.lookupCredentials(
  StringCredentials.class,
  Jenkins.get()
).find { credential -> credential.id == sourceId }

if (source == null) {
  throw new IllegalStateException("Missing Jenkins Secret Text credential: ${sourceId}")
}

def credential = new UsernamePasswordCredentialsImpl(
  CredentialsScope.GLOBAL,
  targetId,
  "GitHub scan credential derived inside Jenkins from Github-Access",
  "x-access-token",
  source.secret.plainText
)

def added = SystemCredentialsProvider.getInstance().getStore().addCredentials(Domain.global(), credential)
if (!added) {
  throw new IllegalStateException("Jenkins did not add credential: ${targetId}")
}

println("Created GitHub scan credential: ${targetId}")
