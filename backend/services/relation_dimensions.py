"""One dimension registry shared by generation, runtime, manual editing and schema."""
RELATION_DIMENSIONS = ('trust', 'affection', 'attraction', 'irritation', 'fear', 'jealousy', 'respect')

RELATION_CONTRACT = ('relationships.dimensions is a closed set: '+', '.join(RELATION_DIMENSIONS)+
    '. Never invent dimension names. Put meaning that does not fit these dimensions in relationship.context.')
