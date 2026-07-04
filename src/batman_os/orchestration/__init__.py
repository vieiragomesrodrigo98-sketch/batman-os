"""Camada de orquestração — não é um Volume da especificação.

Peças de canalização que amarram Kernel (Vol.II) + Runtime (Vol.III) +
Capabilities (Vol.IV) em um fluxo executável de ponta a ponta contra um
repositório real. Nenhum destes módulos redefine comportamento já
especificado — cada um só adapta um Protocol já existente a outro (ex.:
`Operator.execute()` de 3 argumentos ao `OperadorExecutavel.executar()` de 2
que o Execution Engine consome), ou preenche uma peça que a especificação
referencia mas nunca detalha (ex.: quem de fato roteia `capability_id` até um
`handler`).
"""
