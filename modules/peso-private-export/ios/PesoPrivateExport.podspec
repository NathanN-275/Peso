Pod::Spec.new do |s|
  s.name = 'PesoPrivateExport'
  s.version = '1.0.0'
  s.summary = 'Private video export transport for Peso'
  s.homepage = 'https://usepeso.com'
  s.license = 'UNLICENSED'
  s.author = 'Peso'
  s.source = { :path => '.' }
  s.platform = :ios, '16.4'
  s.swift_version = '5.9'
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.source_files = '**/*.swift'
end
